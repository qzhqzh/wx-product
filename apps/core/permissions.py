from rest_framework.permissions import BasePermission


class HasPipelineRole(BasePermission):
    roles = set()

    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return request.user.groups.filter(name__in=self.roles).exists()


class CanCreate(HasPipelineRole):
    roles = {"creator", "planner", "admin"}


class CanReview(HasPipelineRole):
    roles = {"reviewer", "admin"}


class CanOperate(HasPipelineRole):
    roles = {"operator", "reviewer", "admin"}
