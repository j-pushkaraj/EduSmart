# routes/teacher.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import (
    Class, Chapter, Test, Question, TestAttempt, StudentAnswer, User, StudentClass,
    FollowupAssignment
)
from datetime import datetime

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")


# ================================
# ✅ TEACHER DASHBOARD
# ================================
@teacher_bp.route("/dashboard")
@login_required
def dashboard():
    classes = Class.query.filter_by(teacher_id=current_user.id).all()
    return render_template("teacher/dashboard.html", classes=classes)


# ================================
# ✅ CREATE CLASSROOM
# ================================
@teacher_bp.route("/class/create", methods=["GET", "POST"])
@login_required
def create_class():
    if request.method == "POST":
        class_name = request.form.get("name", "").strip()
        join_code = request.form.get("join_code", "").strip()

        if not class_name or not join_code:
            flash("Class name and join code are required!", "danger")
            return redirect(url_for("teacher.create_class"))

        if Class.query.filter_by(join_code=join_code).first():
            flash("❌ Join code already exists. Please use a different one.", "danger")
            return redirect(url_for("teacher.create_class"))

        new_class = Class(name=class_name, join_code=join_code, teacher_id=current_user.id)
        db.session.add(new_class)
        db.session.commit()

        flash("✅ Classroom created successfully!", "success")
        return redirect(url_for("teacher.dashboard"))

    return render_template("teacher/create_class.html")


# ================================
# ✅ VIEW CLASS DETAILS
# ================================
@teacher_bp.route("/class/<int:class_id>")
@login_required
def view_class(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    enrolled_students = [sc.student for sc in class_obj.students]

    for chapter in class_obj.chapters:
        chapter_analytics = get_chapter_analytics(chapter.id)
        chapter.avg_score = chapter_analytics["avg"]
        chapter.lowest_test_name = chapter_analytics["lowest_test"]
        for test in chapter.tests:
            t_analytics = get_test_analytics(test.id)
            test.avg_score = t_analytics["avg"]
            test.highest_score = t_analytics["highest"]
            test.lowest_score = t_analytics["lowest"]

    return render_template(
        "teacher/view_class.html",
        class_obj=class_obj,
        enrolled_students=enrolled_students
    )


# ================================
# ✅ CREATE CHAPTER
# ================================
@teacher_bp.route("/class/<int:class_id>/create_chapter", methods=["GET", "POST"])
@login_required
def create_chapter(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    if request.method == "POST":
        chapter_name = request.form.get("name", "").strip()
        if not chapter_name:
            flash("Chapter name cannot be empty!", "danger")
            return redirect(url_for("teacher.create_chapter", class_id=class_id))

        new_chapter = Chapter(name=chapter_name, class_id=class_id)
        db.session.add(new_chapter)
        db.session.commit()
        flash("✅ Chapter created!", "success")
        return redirect(url_for("teacher.view_class", class_id=class_id))

    return render_template("teacher/create_chapter.html", class_obj=class_obj)


# ================================
# ✅ CREATE TEST
# ================================
@teacher_bp.route("/chapter/<int:chapter_id>/create_test", methods=["GET", "POST"])
@login_required
def create_test(chapter_id):
    chapter_obj = Chapter.query.get_or_404(chapter_id)
    class_obj = Class.query.get(chapter_obj.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    if request.method == "POST":
        test_name = request.form.get("name", "").strip()
        max_score = int(request.form.get("max_score") or 100)
        start_time_str = request.form.get("start_time", "").strip()
        end_time_str = request.form.get("end_time", "").strip()
        duration_minutes = int(request.form.get("duration_minutes") or 30)  # ✅ Dynamic duration

        if not test_name:
            flash("Test name cannot be empty!", "danger")
            return redirect(url_for("teacher.create_test", chapter_id=chapter_id))

        start_time = datetime.fromisoformat(start_time_str) if start_time_str else None
        end_time = datetime.fromisoformat(end_time_str) if end_time_str else None

        new_test = Test(
            name=test_name,
            chapter_id=chapter_id,
            max_score=max_score,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes  # ✅ Save dynamic duration
        )
        db.session.add(new_test)
        db.session.commit()
        flash("✅ Test created! Now add questions.", "success")
        return redirect(url_for("teacher.manage_test", test_id=new_test.id))

    return render_template("teacher/create_test.html", chapter_obj=chapter_obj)

# ================================
# ✅ MANAGE TEST
# ================================
@teacher_bp.route("/test/<int:test_id>/manage", methods=["GET", "POST"])
@login_required
def manage_test(test_id):
    test_obj = Test.query.get_or_404(test_id)
    class_obj = Class.query.get(test_obj.chapter.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    questions = Question.query.filter_by(test_id=test_id).all()
    current_total_marks = sum(q.marks for q in questions if q.marks)

    if request.method == "POST":
        q_text = request.form.get("question_text", "").strip()
        opt_a = request.form.get("option_a", "").strip()
        opt_b = request.form.get("option_b", "").strip()
        opt_c = request.form.get("option_c", "").strip()
        opt_d = request.form.get("option_d", "").strip()
        correct_opt = request.form.get("correct_option", "").strip()
        marks = int(request.form.get("marks") or 1)

        if not q_text or not correct_opt:
            flash("Question text and correct option are required!", "danger")
            return redirect(url_for("teacher.manage_test", test_id=test_id))

        if test_obj.max_score and current_total_marks + marks > test_obj.max_score:
            flash(f"❌ Cannot add question! Total marks would exceed max score ({test_obj.max_score}).", "danger")
            return redirect(url_for("teacher.manage_test", test_id=test_id))

        new_q = Question(
            test_id=test_id,
            text=q_text,
            option_a=opt_a,
            option_b=opt_b,
            option_c=opt_c,
            option_d=opt_d,
            correct_option=correct_opt,
            marks=marks
        )
        db.session.add(new_q)
        db.session.commit()
        flash("✅ Question added successfully!", "success")
        return redirect(url_for("teacher.manage_test", test_id=test_id))

    return render_template(
        "teacher/manage_test.html",
        test_obj=test_obj,
        questions=questions,
        current_total_marks=current_total_marks
    )


# ================================
# ✅ DELETE & EDIT QUESTIONS & TESTS
# ================================
@teacher_bp.route("/question/<int:question_id>/delete", methods=["POST"])
@login_required
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    class_obj = Class.query.get(question.test.chapter.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for("teacher.dashboard"))

    test_id = question.test_id
    db.session.delete(question)
    db.session.commit()
    flash("❌ Question deleted!", "danger")
    return redirect(url_for("teacher.manage_test", test_id=test_id))


@teacher_bp.route("/question/<int:question_id>/edit", methods=["POST"])
@login_required
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    class_obj = Class.query.get(question.test.chapter.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for("teacher.dashboard"))

    question.text = request.form.get("edit_text", "").strip()
    question.option_a = request.form.get("edit_option_a", "").strip()
    question.option_b = request.form.get("edit_option_b", "").strip()
    question.option_c = request.form.get("edit_option_c", "").strip()
    question.option_d = request.form.get("edit_option_d", "").strip()
    question.correct_option = request.form.get("edit_correct_option", "").strip()
    question.marks = int(request.form.get("edit_marks") or question.marks)

    db.session.commit()
    flash("✅ Question updated!", "success")
    return redirect(url_for("teacher.manage_test", test_id=question.test_id))


@teacher_bp.route("/test/<int:test_id>/delete", methods=["POST"])
@login_required
def delete_test(test_id):
    test = Test.query.get_or_404(test_id)
    class_obj = Class.query.get(test.chapter.class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for("teacher.dashboard"))

    class_id = test.chapter.class_id
    db.session.delete(test)
    db.session.commit()
    flash("✅ Test deleted successfully!", "success")
    return redirect(url_for("teacher.view_class", class_id=class_id))


## ================================
# 📘 teacher.py — Updated Analytics Routes
# ================================

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import (
    db, Class, StudentClass, Test, Question, TestAttempt, StudentAnswer,
    AssignmentSubmission, ProctoringLog, RecommendedVideo, Topic,
    FollowupAssignment, User, StudentReview
)




# ================================
# ✅ STUDENT ANALYTICS
# ================================
@teacher_bp.route("/class/<int:class_id>/students")
@login_required
def class_students(class_id):
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    students = (
        db.session.query(User)
        .join(StudentClass)
        .filter(StudentClass.class_id == class_id, User.role == "student")
        .all()
    )

    student_analytics = []
    for student in students:
        attempts = (
            db.session.query(TestAttempt)
            .join(Test)
            .join(Chapter)
            .filter(TestAttempt.student_id == student.id, Chapter.class_id == class_id)
            .all()
        )

        total_attempts = len(attempts)
        total_score = sum(a.score for a in attempts if a.score is not None)
        avg_score = round(total_score / total_attempts, 2) if total_attempts else 0

        weak_topics, strong_topics = [], []

        for attempt in attempts:
            for ans in attempt.answers:
                if ans.question and ans.question.topic:
                    if ans.is_correct:
                        strong_topics.append(ans.question.topic.name)
                    else:
                        weak_topics.append(ans.question.topic.name)

        student_analytics.append({
            "student": student,
            "total_attempts": total_attempts,
            "avg_score": avg_score,
            "weak_topics": list(set(weak_topics)),
            "strong_topics": list(set(strong_topics))
        })

    return render_template(
        "teacher/class_students.html",
        class_obj=class_obj,
        student_analytics=student_analytics
    )

# ================================
# 📊 ANALYTICS HELPERS
# ================================
def get_test_analytics(test_id):
    """Compute average, highest, lowest score for a test."""
    attempts = TestAttempt.query.filter_by(test_id=test_id).all()
    if not attempts:
        return {"avg": 0, "highest": 0, "lowest": 0, "count": 0}

    scores = [a.score for a in attempts if a.score is not None]
    if not scores:
        return {"avg": 0, "highest": 0, "lowest": 0, "count": len(attempts)}

    avg_score = round(sum(scores) / len(scores), 2)
    return {
        "avg": avg_score,
        "highest": max(scores),
        "lowest": min(scores),
        "count": len(scores)
    }


def get_chapter_analytics(chapter_id):
    """Get average and lowest-performing test within a chapter."""
    tests = Test.query.filter_by(chapter_id=chapter_id).all()
    if not tests:
        return {"avg": 0, "lowest_test": None, "total_tests": 0}

    test_scores = {
        test.name: get_test_analytics(test.id)["avg"] for test in tests
    }

    valid_scores = [v for v in test_scores.values() if v > 0]
    if not valid_scores:
        return {"avg": 0, "lowest_test": None, "total_tests": len(tests)}

    avg_score = round(sum(valid_scores) / len(valid_scores), 2)
    lowest_test = min(test_scores, key=test_scores.get)
    return {"avg": avg_score, "lowest_test": lowest_test, "total_tests": len(tests)}

# ================================
# 📈 CLASS ANALYTICS (Overview)
# ================================
@teacher_bp.route("/class/<int:class_id>/analytics")
@login_required
def class_analytics(class_id):
    """Class-level overview: average, weak topics, non-attempts."""
    class_obj = Class.query.get_or_404(class_id)
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    students = (
        db.session.query(User)
        .join(StudentClass)
        .filter(StudentClass.class_id == class_id, User.role == "student")
        .all()
    )

    tests = (
        db.session.query(Test)
        .join(Chapter)
        .filter(Chapter.class_id == class_id)
        .all()
    )

    total_score, total_attempts = 0, 0
    weak_topics = {}

    for test in tests:
        attempts = TestAttempt.query.filter_by(test_id=test.id).all()
        for attempt in attempts:
            if attempt.score:
                total_score += attempt.score
                total_attempts += 1
            for ans in attempt.answers:
                if not ans.is_correct and ans.question and ans.question.topic:
                    topic_name = ans.question.topic.name
                    weak_topics[topic_name] = weak_topics.get(topic_name, 0) + 1

    avg_score = round(total_score / total_attempts, 2) if total_attempts else 0
    weakest_topic = max(weak_topics, key=weak_topics.get) if weak_topics else "N/A"

    attempted_ids = [
        a.student_id for a in db.session.query(TestAttempt)
        .join(Test).join(Chapter)
        .filter(Chapter.class_id == class_id)
        .distinct()
    ]
    not_attempted_students = [s.name for s in students if s.id not in attempted_ids]

    return render_template(
        "teacher/class_analytics.html",
        class_obj=class_obj,
        total_students=len(students),
        avg_score=avg_score,
        weakest_topic=weakest_topic,
        not_attempted_students=not_attempted_students
    )

# ================================
# 🧩 DETAILED TEST REPORT HELPERS
# ================================
from sqlalchemy.orm import aliased

def find_weakest_topic(test_id):
    try:
        QuestionAlias = aliased(Question)
        answers = (
            StudentAnswer.query
            .join(QuestionAlias, StudentAnswer.question_id == QuestionAlias.id)
            .filter(StudentAnswer.test_id == test_id, StudentAnswer.is_correct == False)
            .all()
        )

        if not answers:
            return None

        topic_count = {}
        for ans in answers:
            if ans.question and ans.question.topic:
                topic = ans.question.topic.name
                topic_count[topic] = topic_count.get(topic, 0) + 1

        weakest_topic = max(topic_count, key=topic_count.get) if topic_count else None
        return weakest_topic
    except Exception as e:
        print(f"⚠️ Weakest topic computation failed: {e}")
        return None


from collections import Counter

def calculate_student_score(attempt_id):
    """
    Calculate a student's test score based on correct answers and question marks.
    Returns (obtained_marks, percent).
    """
    attempt = TestAttempt.query.get(attempt_id)
    if not attempt:
        return 0, 0

    answers = StudentAnswer.query.filter_by(attempt_id=attempt_id).all()
    if not answers:
        return 0, 0

    total_marks = 0
    obtained_marks = 0

    for ans in answers:
        question = Question.query.get(ans.question_id)
        if not question:
            continue
        total_marks += question.marks or 1
        if ans.is_correct:
            obtained_marks += question.marks or 1

    percent = round((obtained_marks / total_marks) * 100, 2) if total_marks else 0
    return obtained_marks, percent


def generate_detailed_test_report(test_id):
    """Generate detailed analytics for a test including score stats, weak topics, and improvement."""
    test = Test.query.get_or_404(test_id)
    class_obj = Class.query.get(test.chapter.class_id)

    # === Fetch students and attempts ===
    students = (
        db.session.query(User)
        .join(StudentClass)
        .filter(StudentClass.class_id == class_obj.id, User.role == "student")
        .all()
    )

    attempts = TestAttempt.query.filter_by(test_id=test.id).all()
    total_students = len(students)
    attempted_ids = [a.student_id for a in attempts]
    not_attempted = [s for s in students if s.id not in attempted_ids]

    # === Recalculate all scores dynamically ===
    for a in attempts:
        obtained, percent = calculate_student_score(a.id)
        a.score = obtained
        a.percent = percent if hasattr(a, 'percent') else None
    db.session.commit()

    # === Compute overall stats ===
    scores = [((a.score or 0) / test.max_score) * 100 for a in attempts if test.max_score]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0

    highest_attempt = max(attempts, key=lambda a: a.score or 0, default=None)
    lowest_attempt = min(attempts, key=lambda a: a.score or 0, default=None)

    highest_score = ((highest_attempt.score or 0) / test.max_score) * 100 if highest_attempt else 0
    lowest_score = ((lowest_attempt.score or 0) / test.max_score) * 100 if lowest_attempt else 0
    highest_scorer = User.query.get(highest_attempt.student_id) if highest_attempt else None
    lowest_scorer = User.query.get(lowest_attempt.student_id) if lowest_attempt else None

    # === Build detailed student reports ===
    student_reports = []
    all_remaining_topics = []

    for student in students:
        attempt = next((a for a in attempts if a.student_id == student.id), None)

        # Not attempted
        if not attempt:
            student_reports.append({
                "student": student.name,
                "score": None,
                "percent": None,
                "weak_topics": ["-"],
                "category": "Not Attempted",
                "followup_score": "-",
                "improvement": "-",
                "improvement_display": "-",
                "weak_topics_after_followup": ["-"],
            })
            continue

        # === Compute actual score ===
        obtained, percent = calculate_student_score(attempt.id)

        # === Weak topics ===
        reviews = StudentReview.query.filter_by(student_id=student.id, test_id=test.id).all()
        weak_topics = [r.topic_name for r in reviews if r.topic_name] if reviews else []

        # === Follow-up performance ===
        followups = FollowupAssignment.query.filter_by(student_id=student.id).all()
        followup_attempts = [f for f in followups if f.is_attempted]
        followup_score = 0
        if followup_attempts:
            total_followup = len(followup_attempts)
            correct_followup = sum(1 for f in followup_attempts if f.is_correct)
            followup_score = round((correct_followup / total_followup) * 100, 2)

        # === Remaining Weak Topics ===
        remaining_topics = []
        for f in followup_attempts:
            if not f.is_correct and f.topic_id:
                topic = Topic.query.get(f.topic_id)
                if topic:
                    remaining_topics.append(topic.name)
        remaining_topics = list(set(remaining_topics))
        all_remaining_topics.extend(remaining_topics)

        # === Improvement ===
        improvement = round(followup_score - percent, 2)

        # === Category ===
        if percent >= 85:
            category = "Fast Learner"
        elif percent >= 50:
            category = "Average Learner"
        else:
            category = "Slow Learner"

        # === Perfect scorer (no follow-up needed) ===
        if percent == 100:
            weak_topics = ["No Weak Topics 🎯"]
            remaining_topics = ["No Weak Topics 🎯"]
            followup_score = "Not Required"
            improvement = "Not Required"
            improvement_display = "Not Required"
        else:
            if isinstance(improvement, (int, float)):
                if improvement > 0:
                    improvement_display = f"+{improvement:.1f}%"
                elif improvement < 0:
                    improvement_display = f"{improvement:.1f}%"
                else:
                    improvement_display = "0%"
            else:
                improvement_display = str(improvement)

        student_reports.append({
            "student": student.name,
            "score": percent,
            "percent": percent,
            "weak_topics": weak_topics or ["-"],
            "followup_score": followup_score,
            "improvement": improvement,
            "improvement_display": improvement_display,
            "weak_topics_after_followup": remaining_topics or ["-"],
            "category": category,
        })

    # === Improvement summary ===
    improvements = [r for r in student_reports if isinstance(r["improvement"], (int, float))]
    highest_improvement = max(improvements, key=lambda x: x["improvement"], default=None)
    lowest_improvement = min(improvements, key=lambda x: x["improvement"], default=None)

    # === Weakest topic overall ===
    topic_counter = Counter(t for t in all_remaining_topics if t not in ["No Weak Topics 🎯", "-"])
    if topic_counter:
        max_freq = max(topic_counter.values())
        weakest_topics = [t for t, freq in topic_counter.items() if freq == max_freq]
        weakest_topic_overall = ", ".join(weakest_topics)
    else:
        weakest_topic_overall = "No Weak Topics 🎯"

    # === Final Summary ===
    return {
        "summary": {
            "total_students": total_students,
            "attempted": len(attempts),
            "not_attempted": len(not_attempted),
            "avg_score": avg_score,
            "highest_score": round(highest_score, 2),
            "lowest_score": round(lowest_score, 2),
            "weakest_topic_overall": weakest_topic_overall,
            "highest_scorer": highest_scorer,
            "lowest_scorer": lowest_scorer,
            "highest_improvement": highest_improvement["improvement_display"] if highest_improvement else None,
            "lowest_improvement": lowest_improvement["improvement_display"] if lowest_improvement else None,
            "highest_improvement_student": User.query.filter_by(name=highest_improvement["student"]).first() if highest_improvement else None,
            "lowest_improvement_student": User.query.filter_by(name=lowest_improvement["student"]).first() if lowest_improvement else None,
        },
        "students": student_reports,
        "not_attempted_students": [s.name for s in not_attempted],
    }


# ================================
# 📊 TEST ANALYTICS (Detailed Dashboard View)
# ================================
@teacher_bp.route("/test/<int:test_id>/analytics")
@login_required
def test_analytics(test_id):
    """Detailed analytics dashboard for a test."""
    test = Test.query.get_or_404(test_id)
    class_obj = Class.query.get(test.chapter.class_id)

    # ✅ Authorization check
    if class_obj.teacher_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("teacher.dashboard"))

    # ✅ Generate report
    report = generate_detailed_test_report(test_id)
    if not report:
        flash("Unable to generate report. Please try again later.", "danger")
        return redirect(url_for("teacher.dashboard"))

    return render_template(
        "teacher/test_analytics.html",
        test=test,
        class_obj=class_obj,
        summary=report["summary"],
        student_reports=report["students"],
        not_attempted_students=report["not_attempted_students"],
        report=report
    )
