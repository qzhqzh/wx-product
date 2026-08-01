from rest_framework.permissions import BasePermission

from .runtime_permissions import enforce_runtime_constraints


class HasPipelineRole(BasePermission):
    roles = set()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        enforce_runtime_constraints(request, view)
        if request.user.is_superuser:
            return True
        return request.user.groups.filter(name__in=self.roles).exists()


class CanCreate(HasPipelineRole):
    roles = {"creator", "planner", "admin"}


class CanReview(HasPipelineRole):
    roles = {"reviewer", "admin"}


class CanOperate(HasPipelineRole):
    roles = {"operator", "reviewer", "admin"}
