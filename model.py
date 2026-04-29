"""
=============================================================
  CineAI — Recommendation Model + TMDB Poster Fetching
=============================================================
"""

import pickle
import os
import re
import pandas as pd
import numpy as np
import urllib.request
import json

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, 'models')
DATA_DIR  = os.path.join(BASE_DIR, 'data')

# ─── POSTER CACHE (posters.json se load hota hai) ────────
POSTER_DB     = {}
POSTERS_FILE  = os.path.join(DATA_DIR, 'posters.json')

def _load_poster_db():
    """posters.json load karta hai agar exist kare"""
    global POSTER_DB
    if os.path.exists(POSTERS_FILE):
        with open(POSTERS_FILE, 'r', encoding='utf-8') as f:
            POSTER_DB = json.load(f)
        found = sum(1 for v in POSTER_DB.values() if v.get('poster'))
        print(f"🖼️  Poster DB loaded: {found}/{len(POSTER_DB)} posters available")
    else:
        print("⚠️  posters.json nahi mili — emoji fallback use hoga")
        print("   Poster fetch karne ke liye: python fetch_posters.py")

_load_poster_db()

def get_poster_url(movie_id: int, title: str = '') -> str:
    """
    posters.json se poster URL return karta hai.
    Agar nahi mila toh emoji-based placeholder return karta hai.
    """
    key = str(movie_id)
    if key in POSTER_DB and POSTER_DB[key].get('poster'):
        return POSTER_DB[key]['poster']
    return None   # None means frontend emoji fallback use karega


def get_placeholder_poster(title: str) -> str:
    """TMDB key nahi hai toh genre-based color placeholder return karta hai"""
    # Title ke first letter se color seed banao
    colors = [
        'e94560,1a1a2e', 'e8b84b,0f3460', '4a9eff,080810',
        '95d5b2,1b4332', 'c77dff,10002b', 'ff6b6b,1a1a2e',
        'ffd166,06070e', '06d6a0,073b4c', 'f4a261,264653'
    ]
    idx   = ord(title[0].upper()) % len(colors) if title else 0
    color = colors[idx]
    text  = urllib.parse.quote(title[:15])
    return f"https://via.placeholder.com/300x450/{color.split(',')[0]}/{color.split(',')[1]}?text={text}"


# ─── MODEL LOAD ───────────────────────────────────────────
try:
    import urllib.parse
except ImportError:
    pass

print("🔄 Model files load ho rahi hain...")
try:
    with open(os.path.join(MODEL_DIR,'similarity_matrix.pkl'),'rb') as f:
        SIMILARITY = pickle.load(f)
    with open(os.path.join(MODEL_DIR,'movies_model.pkl'),'rb') as f:
        _data = pickle.load(f)
    with open(os.path.join(MODEL_DIR,'ratings_matrix.pkl'),'rb') as f:
        RATINGS_MATRIX = pickle.load(f)

    DF             = _data['df']
    TITLE_INDEX    = _data['title_to_index']
    TITLE_ORIG_IDX = _data['title_orig_idx']
    print(f"✅ Model ready! {len(DF)} movies available.\n")
except FileNotFoundError:
    print("❌ Model files nahi mili! Pehle preprocess.py chalao.")
    DF = TITLE_INDEX = TITLE_ORIG_IDX = SIMILARITY = RATINGS_MATRIX = None


# ─── SEARCH MOVIE ─────────────────────────────────────────
def search_movies(query: str, limit: int = 8) -> list:
    """Movie naam se search karta hai (autocomplete ke liye)"""
    if DF is None: return []
    query = query.strip().lower()
    if len(query) < 2: return []

    mask    = DF['title_clean'].str.lower().str.contains(query, na=False, regex=False)
    results = DF[mask].copy()

    # Popularity ke basis pe sort karo
    results = results.sort_values('popularity', ascending=False).head(limit)

    return [
        {
            "movieId" : int(row['movieId']),
            "title"   : row['title_clean'],
            "genres"  : row['genres_display'],
            "year"    : int(row['year']) if row['year'] else None,
            "rating"  : float(row['avg_rating']),
            "votes"   : int(row['num_ratings']),
            "poster"  : get_poster_url(int(row['movieId']), row['title_clean'])
        }
        for _, row in results.iterrows()
    ]


# ─── CONTENT-BASED RECOMMENDATIONS ───────────────────────
def get_recommendations(movie_title: str, n: int = 10) -> dict:
    """
    Movie ke naam se similar movies recommend karta hai (Content-Based).
    TF-IDF + Cosine Similarity use karta hai.
    """
    if DF is None:
        return {"status":"error","message":"Model load nahi hua."}

    title_lower = movie_title.strip().lower()

    # 1. Exact match (clean title)
    idx = None
    if title_lower in TITLE_INDEX.index:
        idx = TITLE_INDEX[title_lower]
    # 2. Exact match (original title with year)
    elif title_lower in TITLE_ORIG_IDX.index:
        idx = TITLE_ORIG_IDX[title_lower]
    # 3. Partial match
    else:
        partials = [t for t in TITLE_INDEX.index if title_lower in t]
        if partials:
            # Sabse popular partial match lo
            best = max(partials, key=lambda t: DF.iloc[TITLE_INDEX[t]]['popularity'] if not isinstance(TITLE_INDEX[t], pd.Series) else 0)
            idx = TITLE_INDEX[best]
        else:
            return {
                "status"      : "not_found",
                "message"     : f"'{movie_title}' dataset mein nahi mili.",
                "suggestions" : search_movies(movie_title, 5)
            }

    if isinstance(idx, pd.Series):
        idx = int(idx.iloc[0])
    idx = int(idx)

    # Similarity scores
    sim_scores = list(enumerate(SIMILARITY[idx]))
    sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)[1:n+1]

    recs = []
    for rank, (movie_idx, score) in enumerate(sim_scores, 1):
        row = DF.iloc[movie_idx]
        recs.append({
            "rank"       : rank,
            "movieId"    : int(row['movieId']),
            "title"      : row['title_clean'],
            "genres"     : row['genres_display'],
            "year"       : int(row['year']) if row['year'] else None,
            "rating"     : float(row['avg_rating']),
            "votes"      : int(row['num_ratings']),
            "similarity" : round(float(score), 4),
            "poster"     : get_poster_url(int(row['movieId']), row['title_clean'])
        })

    # Query movie info
    q = DF.iloc[idx]
    query_info = {
        "movieId": int(q['movieId']),
        "title"  : q['title_clean'],
        "genres" : q['genres_display'],
        "year"   : int(q['year']) if q['year'] else None,
        "rating" : float(q['avg_rating']),
        "votes"  : int(q['num_ratings']),
        "poster" : get_poster_url(int(q['movieId']), q['title_clean'])
    }

    return {
        "status"         : "success",
        "query"          : query_info,
        "count"          : len(recs),
        "recommendations": recs
    }


# ─── COLLABORATIVE FILTERING (User-Based) ────────────────
def get_user_recommendations(user_id: int, n: int = 10) -> dict:
    """
    User ID se personalized recommendations (Collaborative Filtering).
    User-based similarity use karta hai.
    """
    if DF is None or RATINGS_MATRIX is None:
        return {"status":"error","message":"Model load nahi hua."}

    if user_id not in RATINGS_MATRIX.index:
        return {
            "status" : "not_found",
            "message": f"User ID {user_id} nahi mila. Valid range: 1–{int(RATINGS_MATRIX.index.max())}"
        }

    # User ki ratings
    user_ratings = RATINGS_MATRIX.loc[user_id]
    watched_ids  = set(user_ratings[user_ratings > 0].index.tolist())

    # Cosine similarity between users
    from sklearn.metrics.pairwise import cosine_similarity as cs
    user_vec     = user_ratings.values.reshape(1, -1)
    all_sims     = cs(user_vec, RATINGS_MATRIX.values)[0]

    # Top 10 similar users (khud ko exclude)
    sim_users_idx = np.argsort(all_sims)[::-1][1:11]
    sim_users     = RATINGS_MATRIX.index[sim_users_idx]

    # Similar users ki movies aggregate karo
    score_dict = {}
    for sim_uid in sim_users:
        sim_ratings = RATINGS_MATRIX.loc[sim_uid]
        for movie_id, rating in sim_ratings.items():
            if rating > 0 and movie_id not in watched_ids:
                score_dict[movie_id] = score_dict.get(movie_id, 0) + rating

    # Top N movies sort karo
    top_movies = sorted(score_dict.items(), key=lambda x: x[1], reverse=True)[:n]

    recs = []
    for rank, (movie_id, score) in enumerate(top_movies, 1):
        row = DF[DF['movieId'] == movie_id]
        if row.empty: continue
        row = row.iloc[0]
        recs.append({
            "rank"    : rank,
            "movieId" : int(row['movieId']),
            "title"   : row['title_clean'],
            "genres"  : row['genres_display'],
            "year"    : int(row['year']) if row['year'] else None,
            "rating"  : float(row['avg_rating']),
            "votes"   : int(row['num_ratings']),
            "cf_score": round(float(score), 2),
            "poster"  : get_poster_url(int(row['movieId']), row['title_clean'])
        })

    # User ne jo dekhi hain unka count
    watched_count = len(watched_ids)

    return {
        "status"         : "success",
        "user_id"        : user_id,
        "movies_watched" : watched_count,
        "count"          : len(recs),
        "recommendations": recs
    }


# ─── TRENDING ─────────────────────────────────────────────
def get_trending(n: int = 12) -> list:
    if DF is None: return []
    top = DF[DF['num_ratings'] >= 20].nlargest(n, 'popularity')
    return _fmt(top)

# ─── TOP RATED ────────────────────────────────────────────
def get_top_rated(n: int = 10) -> list:
    if DF is None: return []
    top = DF[DF['num_ratings'] >= 50].nlargest(n, 'avg_rating')
    return _fmt(top)

# ─── BY GENRE ─────────────────────────────────────────────
def get_by_genre(genre: str, n: int = 12) -> list:
    if DF is None: return []
    if genre.lower() == 'all':
        return get_trending(n)
    mask = DF['genres_display'].str.contains(genre, case=False, na=False)
    top  = DF[mask].nlargest(n, 'popularity')
    return _fmt(top)

# ─── MOVIE DETAIL ─────────────────────────────────────────
def get_movie_detail(movie_id: int) -> dict:
    if DF is None: return {"status":"error"}
    row = DF[DF['movieId'] == movie_id]
    if row.empty:
        return {"status":"not_found","message":f"Movie ID {movie_id} nahi mila"}
    row = row.iloc[0]
    return {
        "status"    : "success",
        "movieId"   : int(row['movieId']),
        "title"     : row['title_clean'],
        "genres"    : row['genres_display'],
        "year"      : int(row['year']) if row['year'] else None,
        "rating"    : float(row['avg_rating']),
        "votes"     : int(row['num_ratings']),
        "popularity": float(row['popularity']),
        "imdb_url"  : str(row['imdb_url']) if pd.notna(row['imdb_url']) else None,
        "poster"    : get_poster_url(int(row['movieId']), row['title_clean'])
    }

# ─── STATS ────────────────────────────────────────────────
def get_stats() -> dict:
    if DF is None: return {}
    genres = set()
    for g in DF['genres_display']:
        for item in str(g).split(','):
            item = item.strip()
            if item and item != 'Unknown':
                genres.add(item)
    return {
        "total_movies"  : int(len(DF)),
        "total_genres"  : int(len(genres)),
        "genres_list"   : sorted(list(genres)),
        "avg_rating"    : round(float(DF['avg_rating'].mean()), 2),
        "total_ratings" : int(DF['num_ratings'].sum()),
        "year_range"    : {
            "min": int(DF[DF['year']>0]['year'].min()),
            "max": int(DF[DF['year']>0]['year'].max())
        }
    }

# ─── HELPER ───────────────────────────────────────────────
def _fmt(df_sub) -> list:
    result = []
    for rank, (_, row) in enumerate(df_sub.iterrows(), 1):
        result.append({
            "rank"      : rank,
            "movieId"   : int(row['movieId']),
            "title"     : row['title_clean'],
            "genres"    : row['genres_display'],
            "year"      : int(row['year']) if row['year'] else None,
            "rating"    : float(row['avg_rating']),
            "votes"     : int(row['num_ratings']),
            "popularity": float(row['popularity']),
            "poster"    : get_poster_url(int(row['movieId']), row['title_clean'])
        })
    return result