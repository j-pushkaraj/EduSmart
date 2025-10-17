# ==============================
# FLASK IMPORTS
# ==============================
from flask import (
    current_app, Blueprint, render_template, request, redirect, flash,
    url_for, session, jsonify
)
from flask_login import current_user, login_required

# ==============================
# DATABASE & MODELS
# ==============================
from models import (
    db, Class, StudentClass, Test, Question, TestAttempt, StudentAnswer,
    AssignmentSubmission, ProctoringLog, RecommendedVideo, Topic,
    FollowupAssignment, User
)
from sqlalchemy.orm import joinedload

# ==============================
# UTILITY IMPORTS
# ==============================
from datetime import datetime, timedelta
import os
import json
import requests
from dotenv import load_dotenv
import threading
import time

# ==============================
# IMAGE / VIDEO PROCESSING
# ==============================
import base64
import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO

# ==============================
# AI / GEMINI
# ==============================
import google.genai as genai
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# single blueprint declaration
student_bp = Blueprint("student", __name__, url_prefix="/student")

# Load env once (optional: do this in app factory instead)
load_dotenv()


# ==============================
# DASHBOARD
# ==============================
@student_bp.route("/dashboard")
@login_required
def dashboard():
    enrolled_classes = (
        db.session.query(Class)
        .join(StudentClass, StudentClass.class_id == Class.id)
        .filter(StudentClass.student_id == current_user.id)
        .all()
    )

    class_tests_status = {}
    now = datetime.now()

    for cls in enrolled_classes:
        class_tests_status[cls.id] = []

        for chapter in cls.chapters:
            for test in chapter.tests:
                attempt = TestAttempt.query.filter_by(
                    student_id=current_user.id, test_id=test.id
                ).first()

                # Determine test status
                if test.start_time <= now <= (
                    test.end_time or (test.start_time + timedelta(minutes=(test.duration_minutes or 0)))
                ):
                    status = "Active"
                elif attempt:
                    status = "Attempted"
                else:
                    status = "Unattempted"

                # Scores
                if attempt:
                    correct = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=True).count()
                    wrong = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=False).count()
                    total_questions = StudentAnswer.query.filter_by(attempt_id=attempt.id).count()
                    score = attempt.score
                else:
                    correct = wrong = total_questions = score = 0

                class_tests_status[cls.id].append({
                    "test": test,
                    "status": status,
                    "correct": correct,
                    "wrong": wrong,
                    "total": total_questions,
                    "score": score,
                })

    return render_template(
        "student/dashboard.html",
        classes=enrolled_classes,
        class_tests_status=class_tests_status,
    )


# ==============================
# JOIN CLASS
# ==============================
@student_bp.route("/join_class", methods=["POST"])
@login_required
def join_class():
    join_code = request.form.get("join_code", "").strip()
    class_obj = Class.query.filter_by(join_code=join_code).first()

    if not class_obj:
        flash("Invalid join code", "danger")
        return redirect(url_for("student.dashboard"))

    already_joined = StudentClass.query.filter_by(
        student_id=current_user.id, class_id=class_obj.id
    ).first()

    if already_joined:
        flash(f"You are already enrolled in {class_obj.name}", "info")
    else:
        new_enrollment = StudentClass(student_id=current_user.id, class_id=class_obj.id)
        db.session.add(new_enrollment)
        db.session.commit()
        flash(f"Successfully joined {class_obj.name}", "success")

    return redirect(url_for("student.dashboard"))


# ==============================
# CLASS DETAIL ROUTE
# ==============================
@student_bp.route("/class/<int:class_id>")
@login_required
def class_detail(class_id):
    class_obj = Class.query.get_or_404(class_id)

    # Check enrollment
    is_enrolled = StudentClass.query.filter_by(student_id=current_user.id, class_id=class_id).first()
    if not is_enrolled:
        flash("You are not enrolled in this class", "danger")
        return redirect(url_for("student.dashboard"))

    # Prepare test attempts dictionary
    attempts = {}
    for chapter in class_obj.chapters:
        for test in chapter.tests:
            attempt = TestAttempt.query.filter_by(student_id=current_user.id, test_id=test.id).first()
            if attempt:
                attempts[test.id] = attempt

    # Prepare assignment submissions dictionary
    submissions = {}
    for assignment in class_obj.assignments:
        submission = AssignmentSubmission.query.filter_by(student_id=current_user.id, assignment_id=assignment.id).first()
        if submission:
            submissions[assignment.id] = submission

    return render_template(
        "student/class_detail.html",
        class_obj=class_obj,
        chapters=class_obj.chapters,
        assignments=class_obj.assignments,
        current_time=datetime.now(),
        attempts=attempts,
        submissions=submissions
    )


# ==============================
# START TEST
# ==============================
@student_bp.route("/start_test/<int:test_id>/<int:question_index>", methods=["GET", "POST"])
@login_required
def start_test(test_id, question_index=0):
    test = Test.query.get_or_404(test_id)
    class_id = test.chapter.class_id
    enrolled = StudentClass.query.filter_by(student_id=current_user.id, class_id=class_id).first()

    if not enrolled:
        flash("You are not enrolled in this class", "danger")
        return redirect(url_for("student.dashboard"))

    now = datetime.now()
    if test.start_time and now < test.start_time:
        flash("⏰ Test has not started yet!", "warning")
        return redirect(url_for("student.dashboard"))
    if test.end_time and now > test.end_time:
        flash("⏰ Test is already over!", "danger")
        return redirect(url_for("student.dashboard"))

    # Retrieve or create attempt
    attempt = TestAttempt.query.filter_by(student_id=current_user.id, test_id=test.id).first()
    if not attempt:
        attempt = TestAttempt(student_id=current_user.id, test_id=test.id, attempted_at=now)
        db.session.add(attempt)
        db.session.commit()

    # Dynamic end_time
    if not attempt.end_time:
        if test.end_time:
            calculated_end = attempt.attempted_at + timedelta(minutes=test.duration_minutes)
            attempt.end_time = min(test.end_time, calculated_end)
        else:
            attempt.end_time = attempt.attempted_at + timedelta(minutes=test.duration_minutes)
        db.session.commit()

    remaining_seconds = int((attempt.end_time - now).total_seconds())
    if remaining_seconds <= 0:
        attempt.correct_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=True).count()
        attempt.wrong_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=False).count()
        attempt.total_questions = len(test.questions)
        attempt.score = attempt.correct_answers
        db.session.commit()
        flash("⏰ Time over! Test submitted automatically.", "danger")
        return redirect(url_for("student.dashboard"))

    questions = test.questions
    total_questions = len(questions)
    if total_questions == 0:
        flash("No questions available for this test!", "info")
        return redirect(url_for("student.class_detail", class_id=class_id))

    if question_index < 0 or question_index >= total_questions:
        return redirect(url_for("student.start_test", test_id=test_id, question_index=0))

    current_question = questions[question_index]
    student_answer = StudentAnswer.query.filter_by(attempt_id=attempt.id, question_id=current_question.id).first()
    options = {"A": current_question.option_a, "B": current_question.option_b,
               "C": current_question.option_c, "D": current_question.option_d}

    # -------------------- POST HANDLER --------------------
    if request.method == "POST":
        selected_option = request.form.get("selected_option")
        mark_review = "mark" in request.form

        if not student_answer:
            student_answer = StudentAnswer(
                attempt_id=attempt.id,
                question_id=current_question.id,
                selected_option=selected_option if selected_option else None,
                is_correct=(selected_option == current_question.correct_option if selected_option else False),
                marked_for_review=mark_review
            )
            db.session.add(student_answer)
        else:
            if selected_option:
                student_answer.selected_option = selected_option
                student_answer.is_correct = selected_option == current_question.correct_option
            student_answer.marked_for_review = mark_review
        db.session.commit()

        # Navigation or submit
        if "next" in request.form and question_index + 1 < total_questions:
            return redirect(url_for("student.start_test", test_id=test.id, question_index=question_index + 1))
        elif "prev" in request.form and question_index > 0:
            return redirect(url_for("student.start_test", test_id=test.id, question_index=question_index - 1))
        elif "submit" in request.form:
            attempt.correct_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=True).count()
            attempt.wrong_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=False).count()
            attempt.total_questions = total_questions
            attempt.score = attempt.correct_answers
            db.session.commit()
            flash("🎉 Test submitted successfully!", "success")
            return redirect(url_for("student.review_test", attempt_id=attempt.id))

    # -------------------- Sidebar State --------------------
    q_states = {}
    for idx, q in enumerate(questions):
        ans = StudentAnswer.query.filter_by(attempt_id=attempt.id, question_id=q.id).first()
        if ans and ans.marked_for_review:
            q_states[idx] = "review"
        elif ans and ans.selected_option:
            q_states[idx] = "answered"
        elif ans or idx == question_index:
            q_states[idx] = "visited"
        else:
            q_states[idx] = "not_visited"

    return render_template(
        "student/start_test.html",
        test=test, current_question=current_question, current_index=question_index,
        total_questions=total_questions, student_answer=student_answer,
        q_states=q_states, remaining_seconds=remaining_seconds,
        options=options, attempt=attempt
    )


# ==============================
# AJAX SAVE ANSWER
# ==============================
@student_bp.route("/ajax_save_answer/<int:test_id>/<int:question_index>", methods=["POST"])
@login_required
def ajax_save_answer(test_id, question_index):
    data = request.get_json()
    action = data.get("action")
    selected_option = data.get("selected_option")

    test = Test.query.get_or_404(test_id)
    attempt = TestAttempt.query.filter_by(student_id=current_user.id, test_id=test.id).first()
    if not attempt:
        return jsonify({"error": "Attempt not found"}), 404

    questions = test.questions
    if question_index < 0 or question_index >= len(questions):
        return jsonify({"error": "Invalid question index"}), 400

    current_question = questions[question_index]
    student_answer = StudentAnswer.query.filter_by(attempt_id=attempt.id, question_id=current_question.id).first()
    if not student_answer:
        student_answer = StudentAnswer(attempt_id=attempt.id, question_id=current_question.id)
        db.session.add(student_answer)

    if action == "mark":
        student_answer.marked_for_review = True
    elif action == "clear":
        student_answer.selected_option = None
        student_answer.is_correct = False
        student_answer.marked_for_review = False
    else:
        if selected_option:
            student_answer.selected_option = selected_option
            student_answer.is_correct = (selected_option == current_question.correct_option)

    db.session.commit()

    if action == "submit":
        attempt.correct_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=True).count()
        attempt.wrong_answers = StudentAnswer.query.filter_by(attempt_id=attempt.id, is_correct=False).count()
        attempt.total_questions = len(questions)
        attempt.score = attempt.correct_answers
        db.session.commit()
        return jsonify({"submit": True})

    # Update q_states & counts
    q_states = {}
    for idx, q in enumerate(questions):
        ans = StudentAnswer.query.filter_by(attempt_id=attempt.id, question_id=q.id).first()
        if ans and ans.marked_for_review:
            q_states[idx] = "review"
        elif ans and ans.selected_option:
            q_states[idx] = "answered"
        elif ans or idx == question_index:
            q_states[idx] = "visited"
        else:
            q_states[idx] = "not_visited"

    counts = {state: list(q_states.values()).count(state) for state in ["answered", "review", "visited", "not_visited"]}

    new_index = question_index
    if action == "next" and question_index + 1 < len(questions):
        new_index += 1
    elif action == "prev" and question_index > 0:
        new_index -= 1

    return jsonify({"q_states": q_states, "counts": counts, "new_index": new_index})


# ==============================
# STUDENT REVIEW TEST (Gemini + YouTube)
# ==============================

@student_bp.route("/review_test/<int:attempt_id>", methods=["GET", "POST"])
@login_required
def review_test(attempt_id):
    # --------------------------
    # 1️⃣ Fetch attempt and test
    # --------------------------
    attempt = (
        TestAttempt.query.filter_by(id=attempt_id, student_id=current_user.id)
        .options(joinedload(TestAttempt.test))
        .first_or_404()
    )
    test = attempt.test

    # --------------------------
    # 2️⃣ Fetch student's answers
    # --------------------------
    answers = (
        StudentAnswer.query.filter_by(attempt_id=attempt.id)
        .join(Question, Question.id == StudentAnswer.question_id)
        .add_entity(Question)
        .all()
    )

    if not answers:
        flash("No review data available for this test yet.", "info")
        return redirect(url_for("student.dashboard"))

    wrongly_attempted = []
    question_weak_topics = {}
    weak_topics = []

    # --------------------------
    # 3️⃣ Identify weak topics
    # --------------------------
    for answer, question in answers:
        if not answer.selected_option or answer.selected_option != question.correct_option:
            wrongly_attempted.append((answer, question))

            topic = Topic.query.filter_by(question_id=question.id).first()
            if not topic:
                try:
                    # Use Gemini API to generate topic
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f'Question: "{question.text}". Identify the most specific academic topic (3–6 words). Only return the topic name.'
                    )
                    topic_name = response.text.strip()
                    topic = Topic(name=topic_name, question_id=question.id)
                    db.session.add(topic)
                    db.session.commit()
                except Exception as e:
                    print("Topic generation error:", e)
                    topic_name = "Unknown Topic"
            else:
                topic_name = topic.name

            question_weak_topics[question.id] = topic_name
            weak_topics.append(topic_name)

    weak_topics = list(set(weak_topics))

    # --------------------------
    # 4️⃣ Prepare videos + followups
    # --------------------------
    topic_data = {}
    for topic_name in weak_topics:
        topic = Topic.query.filter_by(name=topic_name).first()
        if not topic:
            continue

        # ----- YouTube Video -----
        vid = RecommendedVideo.query.filter_by(topic_id=topic.id).first()
        if not vid:
            try:
                search_url = (
                    "https://www.googleapis.com/youtube/v3/search"
                    f"?part=snippet&q={topic_name}+education&type=video&maxResults=1&key={YOUTUBE_API_KEY}"
                )
                resp = requests.get(search_url).json()
                items = resp.get("items", [])
                if items:
                    item = items[0]
                    vid_id = item["id"].get("videoId")
                    if vid_id:
                        video_url = f"https://www.youtube.com/embed/{vid_id}"
                        video_title = item["snippet"]["title"]
                        video_thumbnail = item["snippet"]["thumbnails"]["high"]["url"]

                        # Generate video summary using Gemini
                        summary_resp = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=f"Provide a short educational summary (2-3 lines) of the YouTube video titled '{video_title}'."
                        )
                        video_summary = summary_resp.text.strip()

                        vid = RecommendedVideo(
                            topic_id=topic.id,
                            video_title=video_title,
                            video_url=video_url,
                            video_thumbnail=video_thumbnail,
                            video_summary=video_summary
                        )
                        db.session.add(vid)
                        db.session.commit()
            except Exception as e:
                print("Video fetch error:", e)
                vid = None

        # ----- Follow-up assignments -----
        fas = FollowupAssignment.query.filter_by(
            student_id=current_user.id,
            attempt_id=attempt.id,
            topic_id=topic.id
        ).all()

        if not fas:
            topic_questions = [
                q for _, q in wrongly_attempted if question_weak_topics[q.id] == topic_name
            ][:2]

            for question in topic_questions:
                try:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f'Generate one MCQ similar to "{question.text}". Provide 4 options (A–D) and specify the correct option.'
                    )
                    text = response.text
                    lines = [l.strip() for l in text.split("\n") if l.strip()]

                    qtext, opts, correct = "", {}, ""
                    for line in lines:
                        if line.startswith("Question:"):
                            qtext = line.replace("Question:", "").strip()
                        elif line[:2] in ["A)", "B)", "C)", "D)"]:
                            opts[line[0]] = line[2:].strip()
                        elif "Correct Option" in line:
                            correct = line.split(":")[-1].strip()

                    if qtext:
                        fa = FollowupAssignment(
                            student_id=current_user.id,
                            attempt_id=attempt.id,
                            topic_id=topic.id,
                            question_text=qtext,
                            options=opts,
                            correct_answer=correct
                        )
                        db.session.add(fa)
                        db.session.commit()
                except Exception as e:
                    print("Follow-up gen error:", e)
                    continue

        # Reload after possible additions
        fas = FollowupAssignment.query.filter_by(
            student_id=current_user.id,
            attempt_id=attempt.id,
            topic_id=topic.id
        ).all()

        topic_data[topic_name] = {"video": vid, "followups": fas}

    # --------------------------
    # 5️⃣ Handle follow-up POST
    # --------------------------
    if request.method == "POST":
        correct_count = 0
        total_assignments = 0

        for topic_name, data in topic_data.items():
            for fa in data["followups"]:
                submitted = request.form.get(f"followup_{fa.id}")
                fa.student_answer = submitted
                fa.is_attempted = bool(submitted)
                fa.is_correct = submitted == fa.correct_answer
                if fa.is_correct:
                    correct_count += 1
                total_assignments += 1

        attempt.followup_score = (
            round((correct_count / total_assignments) * 100, 2) if total_assignments else 0
        )
        attempt.followup_attempted = True
        db.session.commit()
        flash("✅ Follow-up submitted successfully!", "success")
        return redirect(url_for("student.review_test", attempt_id=attempt.id))

    # --------------------------
    # 6️⃣ Render
    # --------------------------
    return render_template(
        "student/review_test.html",
        attempt=attempt,
        test=test,
        answers=answers,
        question_weak_topics=question_weak_topics,
        topic_data=topic_data
    )


# ==============================
# PROCTORING: YOLO + Mediapipe
# ==============================
yolo_model = None
face_mesh = None

def get_yolo_model():
    global yolo_model
    if yolo_model is None:
        yolo_model = YOLO("yolov8n.pt")
    return yolo_model

def get_face_mesh():
    global face_mesh
    if face_mesh is None:
        mp_face_mesh = mp.solutions.face_mesh
        face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=0.5)
    return face_mesh

scenario_msgs = {
    "No face detected": "🚨 Hey! We can’t see you on camera. Please sit in front of it.",
    "Multiple people detected": "⚠️ Someone else is nearby. Make sure you’re alone for the test.",
    "Mobile phone detected": "📵 Mobile phone detected! Keep it away during the test.",
    "Eye gaze away": "👀 Looks like your eyes are off the screen. Focus on the test window.",
    "Window switched": "🖥️ You switched tabs! Stay on the test page to continue safely."
}

def check_eye_gaze(landmarks):
    left_eye = np.mean([[landmarks[i].x, landmarks[i].y] for i in [33, 133, 159, 145]], axis=0)
    right_eye = np.mean([[landmarks[i].x, landmarks[i].y] for i in [263, 362, 386, 374]], axis=0)
    eye_center_x = (left_eye[0] + right_eye[0]) / 2
    eye_center_y = (left_eye[1] + right_eye[1]) / 2
    return not (0.35 < eye_center_x < 0.65 and 0.35 < eye_center_y < 0.65)


@student_bp.route("/analyze_frame", methods=["POST"])
@login_required
def analyze_frame():
    data = request.get_json()
    attempt_id = data.get("attempt_id")
    frame_data = data.get("frame")

    if not frame_data:
        return jsonify({"error": "No frame received"}), 400

    # Decode frame
    try:
        frame_data = frame_data.strip()
        img_bytes = base64.b64decode(frame_data.split(",")[1])
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception as e:
        return jsonify({"error": f"Frame decode failed: {str(e)}"}), 500

    # YOLO detection
    try:
        yolo_model = get_yolo_model()
        results = yolo_model(frame, verbose=False)[0]
        detected_objects = [yolo_model.names[int(box.cls)].lower() for box in results.boxes]
        confidences = [float(box.conf) for box in results.boxes]
    except Exception as e:
        return jsonify({"error": f"YOLO detection failed: {str(e)}"}), 500

    face_detected = "person" in detected_objects
    multiple_faces = detected_objects.count("person") > 1
    mobile_detected = any(obj in ["cell phone", "mobile"] and conf > 0.3 for obj, conf in zip(detected_objects, confidences))

    # Eye gaze detection
    eye_gaze_away = False
    try:
        face_mesh_model = get_face_mesh()
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results_face = face_mesh_model.process(rgb_frame)
        if results_face.multi_face_landmarks:
            landmarks = results_face.multi_face_landmarks[0].landmark
            eye_gaze_away = check_eye_gaze(landmarks)
        else:
            face_detected = False
    except Exception as e:
        print(f"[Eye gaze error] {e}")
        eye_gaze_away = False

    # Determine suspicious activity
    suspicious = None
    if not face_detected:
        suspicious = "No face detected"
    elif multiple_faces:
        suspicious = "Multiple people detected"
    elif mobile_detected:
        suspicious = "Mobile phone detected"
    elif eye_gaze_away:
        suspicious = "Eye gaze away"

    # Log to DB
    try:
        log = ProctoringLog(
            attempt_id=attempt_id,
            face_detected=face_detected,
            multiple_faces=multiple_faces,
            mobile_detected=mobile_detected,
            eye_gaze_away=eye_gaze_away,
            suspicious_activity=suspicious,
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"DB logging failed: {str(e)}"}), 500

    # Manage warnings
    warn_key = f"warnings_{current_user.id}_{attempt_id}"
    last_warn_key = f"last_warn_{current_user.id}_{attempt_id}"
    now_ts = time.time()
    session[warn_key] = session.get(warn_key, 0)
    last_warn_time = session.get(last_warn_key, 0)

    if suspicious and (now_ts - last_warn_time > 2):  # Debounce
        session[warn_key] += 1
        session[last_warn_key] = now_ts

    auto_submit = False
    if session.get(warn_key, 0) >= 5:
        auto_submit = True
        session[warn_key] = 0
        session[last_warn_key] = 0

    msg = scenario_msgs.get(suspicious) if suspicious else None

    return jsonify({
        "suspicious": suspicious,
        "msg": msg,
        "warnings": session.get(warn_key, 0),
        "auto_submit": auto_submit
    })
