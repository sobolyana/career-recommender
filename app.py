"""
app.py — Flask server for Career Recommender
"""

from flask import Flask, render_template, request, jsonify
from recommender import run_pipeline

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/recommend', methods=['POST'])
def recommend():
    data = request.get_json()

    # Parse skills from comma-separated string
    skills_raw = data.get('skills', '').strip()
    skills     = [s.strip() for s in skills_raw.split(',') if s.strip()] \
                 if skills_raw else []
    
    job_types = data.get('job_types', [])
    if not job_types:
        job_types = ['Onsite', 'Hybrid', 'Remote'] 

    profile = {
    'bio':           data.get('bio', '').strip(),
    'current_title': data.get('current_title', '').strip(),
    'skills':        skills,
    'target_role':   data.get('target_role', '').strip(),
    'region':        data.get('region', '').strip(),
    'top_k':         int(data.get('top_k', 5)),  
    'job_types':     job_types,
}

    # Validate — need at least bio or skills
    if not profile['bio'] and not profile['skills']:
        return jsonify({'error': 'Please enter a bio or skills to get recommendations'}), 400

    try:
        result = run_pipeline(profile)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Something went wrong: {str(e)}'}), 500


if __name__ == '__main__':
    print('\n🚀 Career Recommender running at http://127.0.0.1:5000\n')
    app.run(debug=False, port=5000)