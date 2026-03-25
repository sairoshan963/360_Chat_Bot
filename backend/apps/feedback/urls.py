from django.urls import path
from . import views

urlpatterns = [
    # Submit feedback for a task
    path('tasks/<uuid:task_id>/submit/', views.SubmitFeedbackView.as_view(), name='feedback-submit'),

    # Employee: my report for a cycle
    path('cycles/<uuid:cycle_id>/my-report/', views.MyReportView.as_view(), name='my-report'),

    # HR: all reports for a cycle
    path('cycles/<uuid:cycle_id>/reports/', views.CycleReportsListView.as_view(), name='cycle-reports'),

    # Manager / HR / Super Admin: specific employee report
    path('cycles/<uuid:cycle_id>/reports/<uuid:employee_id>/', views.EmployeeReportView.as_view(), name='employee-report'),

    # Super Admin: Excel export (single employee)
    path('cycles/<uuid:cycle_id>/reports/<uuid:employee_id>/export/', views.ExportReportView.as_view(), name='export-report'),

    # HR Admin: bulk Excel export (all employees in a cycle)
    path('cycles/<uuid:cycle_id>/reports/export-all/', views.ExportAllReportsView.as_view(), name='export-all-reports'),
]
