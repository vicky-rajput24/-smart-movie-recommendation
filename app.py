"""
=============================================================
  CineAI — Flask Backend API
=============================================================
  Run: python app.py
  URL: http://localhost:5000

  Endpoints:
    GET /api/recommend?movie=Toy+Story&n=10
    GET /api/user?id=42&n=10
    GET /api/search?q=star&limit=8
    GET /api/trending?n=12
    GET /api/toprated?n=10
    GET /api/genre?name=Action&n=12
    GET /api/movie/<id>
    GET /api/stats
=============================================================
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from model import (
    get_recommendations,
    get_user_recommendations,
    search_movies,
    get_trending,
    get_top_rated,
    get_by_genre,
    get_movie_detail,
    get_stats,
    DF
)

app = Flask(__name__, template_folder='../frontend', static_folder='../frontend', static_url_path='')
CORS(app)  # Frontend se API call allow karna 

from auth_routes import auth_bp
app.register_blueprint(auth_bp)



from flask import send_file, redirect
import os
BASE = os.path.dirname(os.path.abspath(__file__))

# ─── AUTH PAGE (Login/Register) ──────────────────────────
@app.route('/')
def auth_page():
    """Root URL pe auth page serve karo"""
    return send_file(os.path.join(BASE, '..', 'frontend', 'auth.html'))

# ─── MAIN APP (Login ke baad redirect yahan hoga) ────────
@app.route('/app')
@app.route('/index.html')
def main_app():
    """Main movie app — login ke baad access hoga"""
    return send_file(os.path.join(BASE, '..', 'frontend', 'index.html'))
#__________

# ─── API INFO ─────────────────────────────────────────────
@app.route('/api')
def api_info():
    return jsonify({
        "app"     : "CineAI Movie Recommendation API",
        "version" : "2.0 — MovieLens 100K Edition",
        "status"  : "running ✅",
        "docs"    : {
            "content_rec"  : "/api/recommend?movie=Toy+Story&n=10",
            "user_rec"     : "/api/user?id=42&n=10",
            "search"       : "/api/search?q=star&limit=8",
            "trending"     : "/api/trending?n=12",
            "top_rated"    : "/api/toprated?n=10",
            "by_genre"     : "/api/genre?name=Action&n=12",
            "movie_detail" : "/api/movie/1",
            "stats"        : "/api/stats"
        }
    })


# ─── CONTENT-BASED RECOMMENDATIONS ───────────────────────
@app.route('/api/recommend')
def recommend():
    """
    Movie naam se similar movies recommend karta hai.
    Example: /api/recommend?movie=Toy+Story&n=10
    """
    movie = request.args.get('movie', '').strip()
    n     = min(int(request.args.get('n', 10)), 20)

    if not movie:
        return jsonify({
            "status" : "error",
            "message": "movie parameter zaroori hai. Example: ?movie=Toy+Story"
        }), 400

    result = get_recommendations(movie, n)
    return jsonify(result)


# ─── COLLABORATIVE FILTERING (User-Based) ────────────────
@app.route('/api/user')
def user_recommend():
    """
    User ID se personalized recommendations.
    Example: /api/user?id=42&n=10
    """
    try:
        user_id = int(request.args.get('id', 0))
    except ValueError:
        return jsonify({"status":"error","message":"id number hona chahiye"}), 400

    n = min(int(request.args.get('n', 10)), 20)

    if user_id <= 0:
        return jsonify({
            "status" : "error",
            "message": "User ID zaroori hai. Example: ?id=42"
        }), 400

    result = get_user_recommendations(user_id, n)
    return jsonify(result)


# ─── SEARCH ──────────────────────────────────────────────
@app.route('/api/search')
def search():
    """
    Movie naam se search karta hai.
    Example: /api/search?q=star&limit=8
    """
    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 8)), 20)

    if len(query) < 2:
        return jsonify({"status":"error","message":"Min 2 characters chahiye"}), 400

    results = search_movies(query, limit)
    return jsonify({
        "status" : "success",
        "query"  : query,
        "count"  : len(results),
        "results": results
    })


# ─── TRENDING ─────────────────────────────────────────────
@app.route('/api/trending')
def trending():
    """Example: /api/trending?n=12"""
    n      = min(int(request.args.get('n', 12)), 30)
    movies = get_trending(n)
    return jsonify({"status":"success","count":len(movies),"movies":movies})


# ─── TOP RATED ────────────────────────────────────────────
@app.route('/api/toprated')
def top_rated():
    """Example: /api/toprated?n=10"""
    n      = min(int(request.args.get('n', 10)), 20)
    movies = get_top_rated(n)
    return jsonify({"status":"success","count":len(movies),"movies":movies})


# ─── GENRE FILTER ─────────────────────────────────────────
@app.route('/api/genre')
def by_genre():
    """Example: /api/genre?name=Action&n=12"""
    genre  = request.args.get('name', 'All').strip()
    n      = min(int(request.args.get('n', 12)), 30)
    movies = get_by_genre(genre, n)
    return jsonify({"status":"success","genre":genre,"count":len(movies),"movies":movies})


# ─── MOVIE DETAIL ─────────────────────────────────────────
@app.route('/api/movie/<int:movie_id>')
def movie_detail(movie_id):
    """Example: /api/movie/1  (Toy Story)"""
    result = get_movie_detail(movie_id)
    if result.get('status') == 'not_found':
        return jsonify(result), 404
    return jsonify(result)


# ─── STATS ────────────────────────────────────────────────
@app.route('/api/stats')
def stats():
    """Dataset statistics"""
    if DF is None:
        return jsonify({"status":"error","message":"Model load nahi hua"}), 500
    data = get_stats()
    data['status'] = 'success'
    return jsonify(data)


# ─── ERROR HANDLERS ──────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"status":"error","message":"Endpoint nahi mila"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"status":"error","message":f"Server error: {str(e)}"}), 500


# ─── MAIN ─────────────────────────────────────────────────
if __name__ == '__main__':
    print("\n" + "="*55)
    print("  🎬  CineAI Flask API — MovieLens 100K Edition")
    print("="*55)
    print("  URL     : http://localhost:5000")
    print("  Test 1  : http://localhost:5000/api/trending")
    print("  Test 2  : http://localhost:5000/api/recommend?movie=Toy+Story")
    print("  Test 3  : http://localhost:5000/api/search?q=star")
    print("  Test 4  : http://localhost:5000/api/user?id=42")
    print("="*55 + "\n")
    app.run(debug=True, port=5000, host='0.0.0.0')