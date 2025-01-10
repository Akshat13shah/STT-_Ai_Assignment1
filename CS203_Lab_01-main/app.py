import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace import SpanKind
import logging

# Flask App Initialization
app = Flask(__name__)
app.secret_key = 'secret'
COURSE_FILE = 'course_catalog.json'

# OpenTelemetry Setup
resource = Resource.create({"service.name": "course-catalog-service"})
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)
span_processor = BatchSpanProcessor(jaeger_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)
FlaskInstrumentor().instrument_app(app)


# Utility Functions
def load_courses():
    """Load courses from the JSON file."""
    if not os.path.exists(COURSE_FILE):
        return []  # Return an empty list if the file doesn't exist
    with open(COURSE_FILE, 'r') as file:
        return json.load(file)


def save_courses(data):
    """Save new course data to the JSON file."""
    courses = load_courses()  # Load existing courses
    courses.append(data)  # Append the new course
    with open(COURSE_FILE, 'w') as file:
        json.dump(courses, file, indent=4)


# def valid()


# Routes
@app.route('/')
def index():
    with tracer.start_as_current_span("index_page", kind=trace.SpanKind.SERVER) as span:
        # Adding trace attributes
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.set_attribute("user.ip", request.remote_addr)  # User's IP address
        return render_template('index.html')


@app.route('/catalog')
def course_catalog():
    with tracer.start_as_current_span("course_catalog", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.add_event("Fetching course catalog")#opentelemtry 2(1)
        courses = load_courses()
        span.add_event("Loaded courses from file", {"course_count": len(courses)})
        return render_template('course_catalog.html', courses=courses)


@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    with tracer.start_as_current_span("add_course", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)#opentelemtry 2(1)
        
        
    if request.method == 'POST':
        with tracer.start_as_current_span("validate_course_form") as validation_span:
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
        span.set_attribute("course.instructor", course.get('instructor', 'Unknown'))#will give unknown as default value 2

        #we will check for the missing required fields 1
        required_fields=['name','instructor']
        missing_fields=[]
        for field in required_fields:
            if not course[field].strip():
                missing_fields.append(field)
                
        if missing_fields:
            validation_span.add_event("Validation failed", {"missing_fields": missing_fields})
            logging.error(f"Missing required fields:{','.join(missing_fields)}")#will log an error of missing fileds
            flash(f"Error:These are the required fileds:{','.join(missing_fields)}","error")#will do flash message
            return render_template('add_course.html')
                
        with tracer.start_as_current_span("save_course_data") as save_span:
            save_courses(course)  # This is the actual function call that saves the course data.
            save_span.add_event("Course saved successfully", {"course_code": course['code']})#for open telemtry
        
        logging.info(f"Course added: {course['code']} - {course['name']} by {course['instructor']}")#Will create a log message 
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
    # Start a span manually for custom tracing
    with tracer.start_as_current_span("manual-span", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", request.url)
        span.add_event("Processing request")
        return "Manual trace recorded!", 200


@app.route("/auto-instrumented")
def auto_instrumented():
    # Automatically instrumented via FlaskInstrumentor
    return "This route is auto-instrumented!", 200


if __name__ == '__main__':
    app.run(debug=True)
