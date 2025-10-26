from extensions import db
from flask_login import UserMixin
from datetime import datetime

# ==========================
# ✅ USER MODEL
# ==========================
class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student' or 'teacher'

    # Relationships
    classes_taught = db.relationship("Class", backref="teacher", lazy=True)
    test_attempts = db.relationship("TestAttempt", backref="student", lazy=True)
    assignment_submissions = db.relationship("AssignmentSubmission", backref="student", lazy=True)
    enrolled_classes = db.relationship("StudentClass", back_populates="student", lazy=True)
    followup_assignments = db.relationship("FollowupAssignment", backref="student", lazy=True)
    analytics = db.relationship("StudentAnalytics", backref="student", lazy=True)
    reviews = db.relationship("StudentReview", back_populates="student", lazy=True)



    def __repr__(self):
        return f"<User {self.name} ({self.role})>"


# ==========================
# ✅ CLASS MODEL
# ==========================
class Class(db.Model):
    __tablename__ = "class"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    join_code = db.Column(db.String(10), unique=True, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Relationships
    students = db.relationship("StudentClass", back_populates="class_obj", lazy=True, cascade="all, delete-orphan")
    chapters = db.relationship("Chapter", backref="class_obj", lazy=True, cascade="all, delete-orphan")
    assignments = db.relationship("Assignment", backref="class_obj", lazy=True, cascade="all, delete-orphan")

    @property
    def enrolled_users(self):
        return [sc.student for sc in self.students]

    def __repr__(self):
        return f"<Class {self.name} | Teacher ID {self.teacher_id}>"


# ==========================
# ✅ MANY-TO-MANY: STUDENT-CLASS
# ==========================
class StudentClass(db.Model):
    __tablename__ = "student_class"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("class.id"), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship("User", back_populates="enrolled_classes", lazy=True)
    class_obj = db.relationship("Class", back_populates="students", lazy=True)

    def __repr__(self):
        return f"<StudentClass student={self.student_id} class={self.class_id}>"


# ==========================
# ✅ CHAPTER MODEL
# ==========================
class Chapter(db.Model):
    __tablename__ = "chapter"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("class.id"), nullable=False)

    tests = db.relationship("Test", backref="chapter", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Chapter {self.name} in Class {self.class_id}>"


# ==========================
# ✅ TEST MODEL
# ==========================
class Test(db.Model):
    __tablename__ = "test"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapter.id"), nullable=False)

    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False)
    max_score = db.Column(db.Integer, default=100)

    # Relationships
    questions = db.relationship("Question", backref="test", lazy=True, cascade="all, delete-orphan")
    attempts = db.relationship("TestAttempt", backref="test", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Test {self.name} | Chapter {self.chapter_id}>"


# ==========================
# ✅ STUDENT TEST ATTEMPTS
# ==========================
class TestAttempt(db.Model):
    __tablename__ = "test_attempt"

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey("test.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    score = db.Column(db.Float, default=0.0)
    attempted_at = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)

    total_questions = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)
    wrong_answers = db.Column(db.Integer, default=0)
    time_taken = db.Column(db.Integer, default=0)

    topic_performance = db.Column(db.JSON, nullable=True)
    auto_submitted_due_to_violation = db.Column(db.Boolean, default=False)
    reviewed = db.Column(db.Boolean, default=False)
    review_completed_at = db.Column(db.DateTime, nullable=True)
    followup_score = db.Column(db.Float, default=None)
    followup_attempted = db.Column(db.Boolean, default=False)
    topic_time = db.Column(db.JSON, nullable=True)  # time spent per topic
    weak_topics_after_followup = db.Column(db.JSON, nullable=True)
   


    answers = db.relationship("StudentAnswer", backref="attempt", lazy=True, cascade="all, delete-orphan")
    followup_assignments = db.relationship("FollowupAssignment", backref="attempt", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Attempt student={self.student_id} test={self.test_id} score={self.score}>"


# ==========================
# ✅ STUDENT ANSWERS
# ==========================
class StudentAnswer(db.Model):
    __tablename__ = "student_answer"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("test_attempt.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)

    selected_option = db.Column(db.String(1), nullable=True)
    is_correct = db.Column(db.Boolean, default=False)
    time_spent = db.Column(db.Integer, default=0)
    marked_for_review = db.Column(db.Boolean, default=False)
    
    question = db.relationship("Question", backref="student_answers", lazy=True)


    def __repr__(self):
        return f"<StudentAnswer question={self.question_id} correct={self.is_correct}>"


# ==========================
# ✅ QUESTION MODEL
# ==========================
class Question(db.Model):
    __tablename__ = "question"

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey("test.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)

    option_a = db.Column(db.String(255), nullable=False)
    option_b = db.Column(db.String(255), nullable=False)
    option_c = db.Column(db.String(255), nullable=False)
    option_d = db.Column(db.String(255), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)

    marks = db.Column(db.Integer, default=1)
    topic = db.Column(db.String(100), nullable=True)
    difficulty = db.Column(db.String(20), nullable=True)

    ai_topic = db.relationship("Topic", backref="question", uselist=False)

    def __repr__(self):
        return f"<Question {self.text[:25]}...>"


# ==========================
# ✅ ASSIGNMENTS
# ==========================
class Assignment(db.Model):
    __tablename__ = "assignment"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey("class.id"), nullable=False)

    submissions = db.relationship("AssignmentSubmission", backref="assignment", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Assignment {self.title}>"


class AssignmentSubmission(db.Model):
    __tablename__ = "assignment_submission"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    score = db.Column(db.Float, default=0.0)
    feedback = db.Column(db.Text, nullable=True)
    improvement_score = db.Column(db.Float, default=0.0)

    def __repr__(self):
        return f"<AssignmentSubmission student={self.student_id} assignment={self.assignment_id}>"


# ==========================
# ✅ ANALYTICS MODEL
# ==========================
class StudentAnalytics(db.Model):
    __tablename__ = "student_analytics"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("class.id"), nullable=False)

    overall_score = db.Column(db.Float, default=0.0)
    weak_topics = db.Column(db.JSON, nullable=True)
    strong_topics = db.Column(db.JSON, nullable=True)
    predicted_weak_topics = db.Column(db.JSON, nullable=True)
    history = db.Column(db.JSON, nullable=True)  # keeps track of every attempt & improvement
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    topic_time = db.Column(db.JSON, nullable=True)          # time per topic across attempts
    followup_progress = db.Column(db.JSON, nullable=True)   # {"Algebra":{"attempted":2,"correct":1,"improvement":20}}
    learning_gaps = db.Column(db.JSON, nullable=True)       # {"Algebra":"Needs extra practice on quadratic equations"}


    def __repr__(self):
        return f"<Analytics student={self.student_id} class={self.class_id}>"



# ==========================
# ✅ PROCTORING
# ==========================
class ProctoringLog(db.Model):
    __tablename__ = "proctoring_log"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("test_attempt.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    face_detected = db.Column(db.Boolean, default=True)
    multiple_faces = db.Column(db.Boolean, default=False)
    mobile_detected = db.Column(db.Boolean, default=False)
    window_switch_detected = db.Column(db.Boolean, default=False)
    eye_gaze_away = db.Column(db.Boolean, default=False)
    suspicious_activity = db.Column(db.String(255), nullable=True)
    warning_level = db.Column(db.Integer, default=0)
    system_message = db.Column(db.String(255), nullable=True)
    auto_submitted = db.Column(db.Boolean, default=False)

    attempt = db.relationship("TestAttempt", backref="proctoring_logs")

    def __repr__(self):
        return f"<ProctoringLog attempt={self.attempt_id} warnings={self.warning_level}>"


class StressLog(db.Model):
    __tablename__ = "stress_log"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("test_attempt.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    detected_emotion = db.Column(db.String(50))
    confidence = db.Column(db.Float, default=0.0)

    attempt = db.relationship("TestAttempt", backref="stress_logs")

    def __repr__(self):
        return f"<StressLog attempt={self.attempt_id} emotion={self.detected_emotion}>"


class ProctoringSummary(db.Model):
    __tablename__ = "proctoring_summary"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("test_attempt.id"), nullable=False)
    total_warnings = db.Column(db.Integer, default=0)
    total_faces_detected = db.Column(db.Integer, default=0)
    total_mobile_detections = db.Column(db.Integer, default=0)
    total_window_shifts = db.Column(db.Integer, default=0)
    last_action = db.Column(db.String(255), nullable=True)

    attempt = db.relationship("TestAttempt", backref="proctoring_summary", uselist=False)

    def __repr__(self):
        return f"<ProctoringSummary attempt={self.attempt_id} warnings={self.total_warnings}>"


# ==========================
# ✅ TOPIC + FOLLOWUP + VIDEO (AI + REVIEW SYSTEM)
# ==========================
class Topic(db.Model):
    __tablename__ = "topic"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(100), nullable=True)
    chapter = db.Column(db.String(100), nullable=True)
    subtopic = db.Column(db.String(100), nullable=True)
    confidence_score = db.Column(db.Float, default=0.0)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    followup_assignments = db.relationship("FollowupAssignment", backref="topic", lazy=True, cascade="all, delete-orphan")
    recommended_videos = db.relationship("RecommendedVideo", backref="topic", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Topic {self.name}>"


class FollowupAssignment(db.Model):
    __tablename__ = "followup_assignment"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id", name="fk_followup_student_id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("topic.id", name="fk_followup_topic_id"), nullable=False)
    attempt_id = db.Column(db.Integer, db.ForeignKey("test_attempt.id", name="fk_followup_attempt_id"), nullable=False)

    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    is_attempted = db.Column(db.Boolean, default=False)
    student_answer = db.Column(db.String(1), nullable=True)
    is_correct = db.Column(db.Boolean, default=False)
    ai_hint = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.String(20), nullable=True)  # easy, medium, hard


    def __repr__(self):
        return f"<FollowupAssignment student={self.student_id} topic={self.topic_id} attempt={self.attempt_id}>"


class RecommendedVideo(db.Model):
    __tablename__ = "recommended_video"

    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topic.id", name="fk_video_topic_id"), nullable=False)

    video_title = db.Column(db.String(255), nullable=False)
    video_url = db.Column(db.String(255), nullable=False)
    channel_name = db.Column(db.String(150), nullable=True)
    views = db.Column(db.Integer, default=0)
    video_summary = db.Column(db.Text, nullable=True)
    video_thumbnail = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<RecommendedVideo topic={self.topic_id} title={self.video_title[:25]}>"


class TopicNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topic.id"))
    content = db.Column(db.Text)

class TopicTrick(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topic.id"))
    content = db.Column(db.Text)


class StudentReview(db.Model):
    __tablename__ = "student_review"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey("test.id"), nullable=False)
    topic_name = db.Column(db.String(150), nullable=False)
    reviewed_on = db.Column(db.DateTime, default=datetime.utcnow)

    test = db.relationship("Test", backref="reviews", lazy=True)
    wrong_questions = db.Column(db.JSON, nullable=True)
    followup_assigned = db.Column(db.Boolean, default=False)
    followup_results = db.Column(db.JSON, nullable=True)
    remaining_weak_topics = db.Column(db.JSON, nullable=True)

    student = db.relationship("User", back_populates="reviews", lazy=True)




    def __repr__(self):
        return f"<StudentReview student={self.student_id} topic={self.topic_name}>"
