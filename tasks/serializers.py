
from rest_framework import serializers
from .models import Task


class TaskSerializer(serializers.ModelSerializer):

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Title cannot contain only whitespace."
            )
        return value.strip()

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Description cannot be empty."
            )

        if len(value) > 500:
            raise serializers.ValidationError(
                "Description cannot be more than 500 characters."
            )

        return value.strip()

    def validate(self, attrs):
        """
        Enforce a maximum hierarchy depth of one:
        Root task -> Subtask.
        A subtask cannot have its own subtasks.
        """

        # Special endpoints can supply the parent through serializer context.
        if "forced_parent" in self.context:
            parent = self.context["forced_parent"]

        # Normal POST/PUT/PATCH requests supply parent in the request body.
        elif "parent" in attrs:
            parent = attrs["parent"]

        # PATCH may omit parent, so retain the existing parent.
        elif self.instance:
            parent = self.instance.parent

        else:
            parent = None

        # Root task: no parent, so hierarchy validation is complete.
        if parent is None:
            return attrs

        # A subtask cannot be used as another task's parent.
        if parent.parent_id is not None:
            raise serializers.ValidationError({
                "parent": "A subtask cannot have its own subtasks."
            })

        # A task that already has subtasks cannot become a subtask itself.
        if self.instance and self.instance.subtasks.exists():
            if self.instance.parent_id is None:
                raise serializers.ValidationError({
                    "parent": "A task with existing subtasks cannot become a subtask."
                })

        # A task cannot be its own parent.
        if self.instance and parent.pk == self.instance.pk:
            raise serializers.ValidationError({
                "parent": "A task cannot be its own parent."
            })

        return attrs
