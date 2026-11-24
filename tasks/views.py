import logging
from rest_framework import viewsets, status
from rest_framework.response import Response

from .models import Task
from .serializers import TaskSerializer
from .utils import error_response, serializer_errors_to_details
from django.http import Http404
from rest_framework.decorators import action
from datetime import date
from .ai import parse_task_text, break_down_task
from django.db import transaction
from copy import deepcopy
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .pagination import TaskPagination

logger = logging.getLogger(__name__)

# In-memory storage for idempotency records
idempotency_store = {}


def check_idempotency(request):
    key = request.headers.get("Idempotency-Key")

    if not key:
        return None, None, None

    # Include the URL because the target task is part of a breakdown request.
    body = {
        "path": request.path,
        "data": deepcopy(request.data)
    }

    existing = idempotency_store.get(key)

    if existing:
        if existing["body"] != body:
            return key, body, error_response(
                "Idempotency key reused with a different request",
                "IDEMPOTENCY_KEY_REUSED",
                [{
                    "field": "Idempotency-Key",
                    "issue": "This key was already used with a different request"
                }],
                422
            )

        # Same key and same request: replay the original response
        return key, body, Response(
            deepcopy(existing["response"]["data"]),
            status=existing["response"]["status"]
        )

    return key, body, None


def save_idempotency_response(key, body, response):
    if key:
        idempotency_store[key] = {
            "body": body,
            "response": {
                "data": deepcopy(response.data),
                "status": response.status_code
            }
        }

class TaskViewSet(viewsets.ModelViewSet):
    
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    filter_backends = [
    DjangoFilterBackend,
    SearchFilter,
    OrderingFilter
    ]

    filterset_fields = ["completed", "priority"]

    search_fields = ["title", "description"]

    ordering_fields = [
        "created_at",
        "updated_at",
        "due_date",
        "priority"
    ]

    ordering = ["-created_at"]

    pagination_class = TaskPagination
    
    def get_task_or_404(self):
        try:
            return self.get_object()
        except Http404:
            return error_response(
                "Task not found",
                "TASK_NOT_FOUND",
                [{"field": "id", "issue": "Task not found"}],
                status.HTTP_404_NOT_FOUND
            )

    def create(self, request, *args, **kwargs):
        key, body, replay = check_idempotency(request)

        if replay is not None:
            return replay

        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                "Validation failed",
                "VALIDATION_ERROR",
                serializer_errors_to_details(serializer.errors),
                status.HTTP_400_BAD_REQUEST
            )

        serializer.save()

        response = Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

        save_idempotency_response(key, body, response)

        return response

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        
        instance = self.get_task_or_404()
        # if the instance is a response, return it
        if isinstance(instance, Response):
            return instance

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial
        )

        if not serializer.is_valid():
            return error_response(
                "Validation failed",
                "VALIDATION_ERROR",
                serializer_errors_to_details(serializer.errors),
                status.HTTP_400_BAD_REQUEST
            )

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_task_or_404()

        if isinstance(instance, Response):
            return instance

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_task_or_404()
        if isinstance(instance, Response):
            return instance

        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    

    @action(detail=False, methods=["post"], url_path="from-text")
    def from_text(self, request):
        key, body, replay = check_idempotency(request)

        if replay is not None:
            return replay

        if not isinstance(request.data, dict):
            return error_response(
                "Validation failed",
                "VALIDATION_ERROR",
                [{"field": "body", "issue": "Request body must be a JSON object"}],
                status.HTTP_400_BAD_REQUEST
            )

        text = request.data.get("text")

        # Validate the incoming text
        if not isinstance(text, str) or not text.strip():
            return error_response(
                "Validation failed",
                "VALIDATION_ERROR",
                [{"field": "text", "issue": "Text must not be empty"}],
                status.HTTP_400_BAD_REQUEST
            )

        # Run the parser
        try:
            parsed_data = parse_task_text(text, date.today())

            if not isinstance(parsed_data, dict):
                raise ValueError("Parser must return a dictionary")

            # Validate parser output using our existing serializer
            serializer = TaskSerializer(data=parsed_data)

            if not serializer.is_valid():
                return error_response(
                    "Parser returned invalid task data",
                    "PARSER_VALIDATION_ERROR",
                    serializer_errors_to_details(serializer.errors),
                    status.HTTP_502_BAD_GATEWAY
                )

            serializer.save()

            response = Response(
            serializer.data,
            status=status.HTTP_201_CREATED
            )

            save_idempotency_response(key, body, response)

            return response

        except Exception:
            logger.exception("Unhandled exception while parsing task text")
            return error_response(
                "Task parsing failed",
                "PARSER_ERROR",
                [{"field": "text", "issue": "Unable to parse task text"}],
                status.HTTP_502_BAD_GATEWAY
            )

   
    @action(detail=True, methods=["get", "post"], url_path="subtasks")
    def subtasks(self, request, pk=None):

        # Find the parent task
        parent_task = self.get_task_or_404()

        if isinstance(parent_task, Response):
            return parent_task

        # A subtask cannot have its own subtasks
        if parent_task.parent_id is not None:
            return error_response(
                "A subtask cannot have its own subtasks",
                "INVALID_PARENT",
                [{"field": "parent", "issue": "Subtasks cannot contain subtasks"}],
                status.HTTP_400_BAD_REQUEST
            )

        # GET: List all subtasks
        if request.method == "GET":
            serializer = TaskSerializer(
                parent_task.subtasks.all(),
                many=True
            )
            return Response(serializer.data, status=status.HTTP_200_OK)

        # POST: Create one subtask
        serializer = TaskSerializer(
            data=request.data,
            context={
                **self.get_serializer_context(),
                "forced_parent": parent_task
            }
        )

        if not serializer.is_valid():
            return error_response(
                "Validation failed",
                "VALIDATION_ERROR",
                serializer_errors_to_details(serializer.errors),
                status.HTTP_400_BAD_REQUEST
            )

        # Save with the parent task from the URL
        serializer.save(parent=parent_task)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )


    @action(detail=True, methods=["post"], url_path="breakdown")
    def breakdown(self, request, pk=None):
        key, body, replay = check_idempotency(request)

        if replay is not None:
            return replay

        # Find the parent task
        task = self.get_task_or_404()

        if isinstance(task, Response):
            return task

        # Prevent breaking down a subtask
        if task.parent_id is not None:
            return error_response(
                "A subtask cannot be broken down",
                "INVALID_PARENT",
                [{"field": "parent", "issue": "Subtasks cannot contain subtasks"}],
                status.HTTP_400_BAD_REQUEST
            )

        # Generate subtask data
        try:
            subtasks_data = break_down_task(task)

            if not isinstance(subtasks_data, list) or not subtasks_data:
                return error_response(
                    "No subtasks could be generated",
                    "BREAKDOWN_ERROR",
                    [{"field": "description", "issue": "No valid subtasks generated"}],
                    status.HTTP_400_BAD_REQUEST
                )

            # Validate ALL subtasks before saving ANY
            serializers = [
                TaskSerializer(
                    data=item,
                    context={
                        **self.get_serializer_context(),
                        "forced_parent": task
                    }
                )
                for item in subtasks_data
            ]

            all_valid = True
            details = []

            for serializer in serializers:
                if not serializer.is_valid():
                    all_valid = False
                    details.extend(
                        serializer_errors_to_details(serializer.errors)
                    )

            if not all_valid:
                return error_response(
                    "Generated subtasks are invalid",
                    "BREAKDOWN_VALIDATION_ERROR",
                    details,
                    status.HTTP_502_BAD_GATEWAY
                )

            # Save all subtasks together
            with transaction.atomic():
                created_subtasks = [
                    serializer.save(parent=task)
                    for serializer in serializers
                ]

            response_serializer = TaskSerializer(
                created_subtasks,
                many=True
            )

            response = Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )

            save_idempotency_response(key, body, response)

            return response

        except Exception:
            logger.exception("Unhandled exception while breaking down task")
            return error_response(
                "Task breakdown failed",
                "BREAKDOWN_ERROR",
                [{"field": "task", "issue": "Unable to break down task"}],
                status.HTTP_502_BAD_GATEWAY
            )
    
    @action(detail=False, methods=["get"],url_path=r"priority/(?P<level>[^/.]+)")
    def priority(self, request, level=None):

        # Validate priority level
        valid_priorities = Task.Priority.values

        if level not in valid_priorities:
            return error_response(
                "Invalid priority level",
                "INVALID_PRIORITY",
                [{
                    "field": "priority",
                    "issue": "Priority must be low, medium, or high"
                }],
                status.HTTP_400_BAD_REQUEST
            )

        tasks = Task.objects.filter(priority=level)

        serializer = TaskSerializer(tasks, many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )