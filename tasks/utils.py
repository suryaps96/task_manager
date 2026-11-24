from rest_framework.response import Response




def error_response(message, code, details, status_code):
    return Response(
    {
        "error": {
            "code": str(code),
            "message": str(message),
            "details": details
        }
    },
    status=status_code
)

def serializer_errors_to_details(errors):
    details = []

    for field, issues in errors.items():
        for issue in issues:
            details.append({
                "field": field,
                "issue": str(issue)
            })

    return details
    