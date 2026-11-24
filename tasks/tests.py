
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

from .serializers import TaskSerializer


class TaskSerializerTest(TestCase):

    def test_valid_task_data(self):
        data = {
            "title": "Learn Django REST Framework",
            "description": "Build my first API",
            "completed": False,
            "priority": "high"
        }

        serializer = TaskSerializer(data=data)

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_whitespace_only_title(self):
        data = {
            "title": "     ",
            "description": "Learn DRF",
            "completed": False,
            "priority": "high"
        }

        serializer = TaskSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("title", serializer.errors)
    
    def test_invalid_priority(self):
        data = {
            "title": "Learn DRF",
            "description": "Learn serializers",
            "completed": False,
            "priority": "urgent"
        }

        serializer = TaskSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("priority", serializer.errors)
    
    def test_description_exceeds_500_characters(self):
        data = {
            "title": "Learn DRF",
            "description": "A" * 501,
            "completed": False,
            "priority": "high"
        }

        serializer = TaskSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("description", serializer.errors)
    
    
    def test_due_date_is_optional(self):
        data = {
            "title": "Learn Django",
            "description": "Practise serializers",
            "completed": False,
            "priority": "medium"
        }

        serializer = TaskSerializer(data=data)

        self.assertTrue(serializer.is_valid(), serializer.errors)
    
    def test_valid_task_can_be_saved(self):
        data = {
            "title": "Learn Django",
            "description": "Practise serializers",
            "completed": False,
            "priority": "high"
        }

        serializer = TaskSerializer(data=data)

        self.assertTrue(serializer.is_valid(), serializer.errors)

        task = serializer.save()

        self.assertIsNotNone(task.id)
        self.assertEqual(task.title, "Learn Django")
    

    def test_impossible_due_date(self):
        data = {
            "title": "Pay rent",
            "description": "Monthly rent payment",
            "completed": False,
            "due_date": "2026-02-30",
            "priority": "high"
        }

        serializer = TaskSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("due_date", serializer.errors)

    def test_valid_due_date(self):
        data = {
            "title": "Pay rent",
            "description": "Monthly rent payment",
            "completed": False,
            "due_date": "2026-02-28",
            "priority": "high"
        }

        serializer = TaskSerializer(data=data)

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_empty_description(self):
        data = {
            "title": "Pay rent",
            "description": "",
            "completed": False,
            "priority": "medium"
        }

        serializer = TaskSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("description", serializer.errors)
    
    def test_whitespace_only_description(self):
        data = {
            "title": "Pay rent",
            "description": "     ",
            "completed": False,
            "priority": "medium"
        }

        serializer = TaskSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("description", serializer.errors)
    
    def test_invalid_completed_value(self):
        data = {
            "title": "Pay rent",
            "description": "Monthly rent payment",
            "completed": "maybe",
            "priority": "medium"
        }

        serializer = TaskSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("completed", serializer.errors)

