
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
import logging

# ✅ Import ALL models referenced in views
from .models import Course, Enrollment, Question, Choice, Submission

logger = logging.getLogger(__name__)

def registration_request(request):
    context = {}
    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)
    elif request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']
        user_exist = False
        try:
            User.objects.get(username=username)
            user_exist = True
        except Exception:
            logger.info("New user")
        if not user_exist:
            user = User.objects.create_user(
                username=username, first_name=first_name, last_name=last_name, password=password
            )
            login(request, user)
            return redirect("onlinecourse:index")
        else:
            context['message'] = "User already exists."
            return render(request, 'onlinecourse/user_registration_bootstrap.html', context)

def login_request(request):
    context = {}
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')
        else:
            context['message'] = "Invalid username or password."
            return render(request, 'onlinecourse/user_login_bootstrap.html', context)
    else:
        return render(request, 'onlinecourse/user_login_bootstrap.html', context)

def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')

def check_if_enrolled(user, course):
    if user.id is None:
        return False
    return Enrollment.objects.filter(user=user, course=course).exists()

class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]
        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)
        return courses

class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'

@login_required
def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if not check_if_enrolled(user, course):
        Enrollment.objects.create(user=user, course=course, mode='honor')
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(reverse(viewname='onlinecourse:course_details', args=(course.id,)))

# ✅ Robustly collect selected choice IDs from POST
def extract_answers(request):
    selected_ids = set()
    # Case 1: checkbox inputs with the same name="choice"
    for cid in request.POST.getlist('choice'):
        try:
            selected_ids.add(int(cid))
        except (TypeError, ValueError):
            pass
    # Case 2: inputs named like choice_<id>=<id>
    for key, value in request.POST.items():
        if key.startswith('choice_'):
            try:
                selected_ids.add(int(value))
            except (TypeError, ValueError):
                pass
    return list(selected_ids)

@login_required
def submit(request, course_id):
    if request.method != "POST":
        return HttpResponseForbidden("Invalid method")

    course = get_object_or_404(Course, pk=course_id)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)

    submission = Submission.objects.create(enrollment=enrollment)

    choice_ids = extract_answers(request)
    selected_choices = Choice.objects.filter(id__in=choice_ids)
    submission.choices.set(selected_choices)
    submission.save()

    # 🔁 Make sure this URL name matches your urls.py
    # If your urls.py names it "show_exam_result", use that.
    return redirect('onlinecourse:exam_result', course_id=course.id, submission_id=submission.id)
    # Alternatively:
    # return HttpResponseRedirect(reverse('onlinecourse:show_exam_result', args=(course.id, submission.id)))

@login_required
def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(Submission, pk=submission_id)

    # IDs of choices selected in this submission
    selected_ids = set(submission.choices.values_list('id', flat=True))

    total_score = 0
    obtained = 0

    # If your Question has a FK to Course, this is fine. Otherwise adapt the filter.
    for question in Question.objects.filter(course=course):
        # If your model uses a different field name than 'grade', update here.
        question_grade = getattr(question, 'grade', 1)
        total_score += question_grade

        correct_ids = set(
            question.choice_set.filter(is_correct=True).values_list('id', flat=True)
        )
        chosen_for_q = set(
            submission.choices.filter(question=question).values_list('id', flat=True)
        )

        # Award only if the selection exactly matches the set of correct answers
        if chosen_for_q == correct_ids:
            obtained += question_grade

    score_percent = round((obtained / total_score) * 100, 2) if total_score else 0

    context = {
        "course": course,
        "submission": submission,
        "selected_ids": selected_ids,
        "obtained": obtained,
        "total": total_score,
        "score_percent": score_percent,
    }
    return render(request, 'onlinecourse/exam_result_bootstrap.html', context)
