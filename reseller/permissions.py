from rest_framework import permissions


class ActiveResellerPermission(permissions.BasePermission):
    message = "Deposit the minimum amount to activate your reseller panel."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        reseller = getattr(request.user, "reseller", None)
        return bool(reseller and reseller.can_operate)
