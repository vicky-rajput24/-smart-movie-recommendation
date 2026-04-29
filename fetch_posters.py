"""
=============================================================
  CineAI — TMDB Poster Fetcher
  MovieLens 1682 movies ke posters ek baar fetch karke
  data/posters.json mein save karta hai.
=============================================================
  Run: python fetch_posters.py
  
  Pehle TMDB_API_KEY set karo neeche.
  themoviedb.org → Settings → API → API Key (v3 auth)
=============================================================
"""
import json
import os
import time
import re
import urllib.request
import urllib.parse
import pickle

# ─── CONFIG ───────────────────────────────────────────────
TMDB_API_KEY = "78ad1646b4b707dd4edc244406d49d29"   # ← Yahan apni key daalo

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR   = os.path.join(BASE_DIR, 'models')
DATA_DIR    = os.path.join(BASE_DIR, 'data')
OUTPUT_FILE = os.path.join(DATA_DIR, 'posters.json')

TMDB_SEARCH   = "https://api.themoviedb.org/3/search/movie"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"

# ─── VALIDATION ───────────────────────────────────────────
if TMDB_API_KEY == "APNA_KEY_YAHAN_DAALO":
    print("❌ Pehle TMDB API key daalo!")
    print("   fetch_posters.py open karo")
    print("   Line 19 mein: TMDB_API_KEY = 'teri_key_yahan'")
    exit(1)

model_path = os.path.join(MODEL_DIR, 'movies_model.pkl')
if not os.path.exists(model_path):
    print("❌ movies_model.pkl nahi mili!")
    print("   Pehle preprocess.py chalao: python preprocess.py")
    exit(1)

# ─── LOAD MOVIES ──────────────────────────────────────────
print("📂 Movies load ho rahi hain...")
with open(model_path, 'rb') as f:
    data = pickle.load(f)
df = data['df']
print(f"✅ {len(df)} movies mili!\n")

# ─── HELPER FUNCTIONS ─────────────────────────────────────
def clean_for_search(title: str) -> str:
    """
    Title se extra cheezein hatata hai TMDB search ke liye.
    'The Matrix (1999)' → 'The Matrix'
    'Star Wars: Episode IV' → 'Star Wars Episode IV'
    """
    title = re.sub(r'\s*\(\d{4}\)\s*', '', title).strip()
    title = re.sub(r'[:\-]', ' ', title).strip()
    return title

def search_tmdb(title: str, year: int = 0) -> dict | None:
    """TMDB se movie search karta hai, best match return karta hai"""
    try:
        query    = urllib.parse.quote(clean_for_search(title))
        url      = f"{TMDB_SEARCH}?api_key={TMDB_API_KEY}&query={query}&language=en-US"
        if year and year > 0:
            url += f"&year={year}"

        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'CineAI/1.0', 'Accept': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        results = data.get('results', [])
        if results:
            # Poster wali pehli movie return karo
            for r in results:
                if r.get('poster_path'):
                    return r
        return None

    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(f"\n❌ API Key galat hai! Check karo.")
            exit(1)
        return None
    except Exception:
        return None


def get_poster_url(tmdb_result: dict) -> str | None:
    """TMDB result se poster URL banata hai"""
    if tmdb_result and tmdb_result.get('poster_path'):
        return TMDB_IMG_BASE + tmdb_result['poster_path']
    return None


# ─── LOAD EXISTING CACHE ──────────────────────────────────
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        posters = json.load(f)
    print(f"📦 Existing cache mila: {len(posters)} posters already saved")
    print("   Sirf missing movies fetch hongi...\n")
else:
    posters = {}
    print("🆕 Naya posters.json create ho raha hai\n")


# ─── FETCH POSTERS ────────────────────────────────────────
total       = len(df)
fetched     = 0
skipped     = 0
failed      = 0
already_had = 0

print("=" * 60)
print(f"  Fetching posters for {total} movies...")
print(f"  TMDB API Rate Limit: 40 req/10 sec — Auto handled ✅")
print("=" * 60 + "\n")

for i, (_, row) in enumerate(df.iterrows()):
    title      = str(row['title_clean'])
    movie_id   = int(row['movieId'])
    year       = int(row['year']) if row['year'] and row['year'] > 0 else 0
    cache_key  = str(movie_id)

    # Already cached hai?
    if cache_key in posters:
        already_had += 1
        continue

    # TMDB search
    result     = search_tmdb(title, year)
    poster_url = get_poster_url(result)

    if poster_url:
        posters[cache_key] = {
            "movieId"   : movie_id,
            "title"     : title,
            "poster"    : poster_url,
            "tmdb_id"   : result.get('id'),
            "overview"  : result.get('overview', '')[:300],
            "tmdb_rating": result.get('vote_average', 0)
        }
        fetched += 1
        status = "✅"
    else:
        posters[cache_key] = {
            "movieId": movie_id,
            "title"  : title,
            "poster" : None
        }
        failed += 1
        status = "❌"

    # Progress print
    done = i + 1
    pct  = (done / total) * 100
    print(f"  [{done:4d}/{total}] {pct:5.1f}% {status} {title[:45]}")

    # Har 10 movies pe save karo (crash protection)
    if done % 10 == 0:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(posters, f, ensure_ascii=False, indent=2)

    # Rate limit: 40 req/10 sec → 0.25 sec per request safe hai
    time.sleep(0.27)

    # Har 100 movies pe summary
    if done % 100 == 0:
        print(f"\n  📊 Progress: {fetched} posters | {failed} failed | {already_had} cached")
        print(f"  ⏱️  ~{int((total-done)*0.27/60)} min remaining\n")


# ─── FINAL SAVE ───────────────────────────────────────────
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(posters, f, ensure_ascii=False, indent=2)

# ─── SUMMARY ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("  ✅ POSTER FETCHING COMPLETE!")
print("=" * 60)
print(f"  ✅ Fetched      : {fetched}")
print(f"  📦 From cache   : {already_had}")
print(f"  ❌ Not found    : {failed}")
print(f"  📁 Saved to     : {OUTPUT_FILE}")
coverage = ((fetched + already_had) / total) * 100
print(f"  📊 Coverage     : {coverage:.1f}% movies have posters")
print(f"\n  ▶️  Ab app.py chalao: python app.py")
print("=" * 60)
