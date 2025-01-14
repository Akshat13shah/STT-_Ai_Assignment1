import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace import SpanKind
import logging  # to import logging


# Flask App Initialization
app = Flask(__name__)
app.secret_key = 'secret'
COURSE_FILE = 'CS203_Lab_01-main\\course_catalog.json'

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Configure logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger_name': record.name,
            'path': record.pathname,
            'line': record.lineno,
        }
        return json.dumps(log_record)

logger = logging.getLogger(__name__)
file_handler = logging.FileHandler('tracers.json')
file_handler.setFormatter(JsonFormatter())
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)

# OpenTelemetry Setup



# Example usage
tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("example-console-span"):
    print("This span will be printed to the console.")


resource = Resource.create({"service.name": "course-catalog-service"})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)
# Create a ConsoleSpanExporter
console_exporter = ConsoleSpanExporter()

# Configure the BatchSpanProcessor
span_processor = BatchSpanProcessor(console_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# span_processor = BatchSpanProcessor(jaeger_exporter)
# trace.get_tracer_provider().add_span_processor(span_processor)

FlaskInstrumentor().instrument_app(app)

# Global error_count for tracking errors
error_count = 0

# Utility Functions
def load_courses():
    """Load courses from the JSON file."""
    if not os.path.exists(COURSE_FILE):
        return []  # Return an empty list if the file doesn't exist
    with open(COURSE_FILE, 'r') as file:
        return json.load(file)


def save_courses(data):
    """Save new course data to the JSON file."""
    global error_count
    required_fields = ['code', 'name', 'instructor']
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    
    if missing_fields:
        error_message = f"Missing required fields: {', '.join(missing_fields)}"
        app.logger.error(error_message)
        flash(error_message, "error")
        error_count += 1
        with tracer.start_as_current_span("save_courses_error", kind=SpanKind.INTERNAL) as span:
            span.set_attribute("error.type", "MissingFields")
            span.set_attribute("error.count", error_count)  # Count as one error
            span.add_event(error_message)
        return
    
    courses = load_courses()  # Load existing courses
    courses.append(data)  # Append the new course
    try:
        with open(COURSE_FILE, 'w') as file:
            json.dump(courses, file, indent=4)
        app.logger.info(f"Course '{data['name']}' added with code '{data['code']}'")
    except Exception as e:
        error_count += 1
        app.logger.error(f"Error saving course data: {str(e)}")
        with tracer.start_as_current_span("save_courses_error", kind=SpanKind.INTERNAL) as span:
            span.set_attribute("error.type", "FileWriteError")
            span.set_attribute("error.count", error_count)
            span.add_event(f"Error saving course data: {str(e)}")


# Routes
@app.route('/')
def index():
    with tracer.start_as_current_span("index_page", kind=trace.SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.set_attribute("user.ip", request.remote_addr)  # User's IP address
        logger.info("Rendering index page", extra={"http.method": request.method, "http.url": request.url, "user.ip": request.remote_addr})
        return render_template('index.html')


@app.route('/catalog')
def course_catalog():
    with tracer.start_as_current_span("course_catalog", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.add_event("Fetching course catalog")
        logger.info("Fetching course catalog", extra={"http.method": request.method, "http.url": request.url})
        
        courses = load_courses()
        span.add_event("Loaded courses from file", {"course_count": len(courses)})
        logger.info("Loaded courses from file", extra={"course_count": len(courses)})
        return render_template('course_catalog.html', courses=courses)


@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    global error_count
    with tracer.start_as_current_span("add_course", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        logger.info("Accessed add_course route", extra={"http.method": request.method, "http.url": request.url})
        
    if request.method == 'POST':
        with tracer.start_as_current_span("validate_course_form") as validation_span:
            logger.info("Form submitted")
            course = {
                'code': request.form['code'],
                'name': request.form['name'],
                'instructor': request.form['instructor'],
                'semester': request.form['semester'],
                'schedule': request.form['schedule'],
                'classroom': request.form['classroom'],
                'prerequisites': request.form['prerequisites'],
                'grading': request.form['grading'],
                'description': request.form['description']
            }

        span.set_attribute("course.name", course.get('name', 'Unknown'))
        span.set_attribute("course.instructor", course.get('instructor', 'Unknown'))

        # Check for missing required fields
        required_fields = ['code', 'name', 'instructor']
        missing_fields = []
        for field in required_fields:
            if not course.get(field, '').strip():
                missing_fields.append(field)
                
        if missing_fields:
            validation_span.add_event("Validation failed", {"missing_fields": missing_fields})
            logger.error(f"Missing required fields: {','.join(missing_fields)}")
            flash(f"Error: These are the required fields: {','.join(missing_fields)}", "error")
            error_count += 1
            with tracer.start_as_current_span("save_courses_error", kind=SpanKind.INTERNAL) as span:
                span.set_attribute("error.type", "MissingFields")
                span.set_attribute("error.count", error_count)
                span.add_event(f"Missing fields: {','.join(missing_fields)}")
            return render_template('add_course.html')
                
        with tracer.start_as_current_span("save_course_data") as save_span:
            save_courses(course)  # This is the actual function call that saves the course data.
            save_span.add_event("Course saved successfully", {"course_code": course['code']})
        
        logger.info(f"Course added: {course['code']} - {course['name']} by {course['instructor']}")
        flash(f"Course '{course['name']}' added successfully!", "success")
        return redirect(url_for('course_catalog'))
    return render_template('add_course.html')


@app.route('/course/<code>')
def course_details(code):
    with tracer.start_as_current_span("course_details", kind=SpanKind.SERVER) as span:
       span.set_attribute("http.method", request.method)
       span.set_attribute("http.url", request.url)
       span.set_attribute("course.code", code)
       
       courses = load_courses()
       course = next((course for course in courses if course['code'] == code), None)
       
    if not course:
        span.add_event("Course not found", {"course_code": code})
        flash(f"No course found with code '{code}'.", "error")
        return redirect(url_for('course_catalog'))
    
    span.add_event("Course details fetched", {"course_name": course['name']})
    return render_template('course_details.html', course=course)


@app.route("/manual-trace")
def manual_trace():
    with tracer.start_as_current_span("manual-span", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.add_event("Processing request")
        return "Manual trace recorded!", 200


@app.route("/auto-instrumented")
def auto_instrumented():
    return "This route is auto-instrumented!", 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
