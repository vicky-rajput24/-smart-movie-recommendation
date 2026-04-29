"""
=============================================================
  CineAI — Preprocessing for MovieLens 100K Dataset
=============================================================
  ml-100k folder mein ye files honi chahiye:
    backend/data/ml-100k/u.data   (ratings)
    backend/data/ml-100k/u.item   (movies)
    backend/data/ml-100k/u.genre  (genre names)

  Run: python preprocess.py
  Output:
    backend/data/movies_clean.csv
    backend/models/similarity_matrix.pkl
    backend/models/movies_model.pkl
    backend/models/ratings_matrix.pkl
=============================================================
"""

import pandas as pd
import numpy as np
import os
import re
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ─── PATHS ────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, 'data', 'ml-100k')
OUT_DIR   = os.path.join(BASE_DIR, 'data')
MODEL_DIR = os.path.join(BASE_DIR, 'models')
os.makedirs(MODEL_DIR, exist_ok=True)

print("=" * 60)
print("  CineAI — MovieLens 100K Preprocessing")
print("=" * 60)

# ─── CHECK FILES ──────────────────────────────────────────
for fname in ['u.data', 'u.item', 'u.genre']:
    path = os.path.join(DATA_DIR, fname)
    if not os.path.exists(path):
        print(f"\n❌ File is not avaible: {path}")
        print(f"   ml-100k folder yahan rakh do: {DATA_DIR}")
        exit(1)
print("✅ Saari files ready!\n")

# ─── STEP 1: GENRE NAMES ─────────────────────────────────
print("Step 1: Genre names load kar raha hai...")
genre_names = []
with open(os.path.join(DATA_DIR, 'u.genre'), 'r') as f:
    for line in f:
        line = line.strip()
        if '|' in line:
            name, _ = line.split('|')
            genre_names.append(name.strip())
print(f"  ✅ Genres: {genre_names}\n")

# ─── STEP 2: MOVIES ──────────────────────────────────────
print("Step 2: Movies load kar raha hai...")
movie_cols = ['movieId','title','release_date','video_release','imdb_url'] + \
             [f'g_{i}' for i in range(len(genre_names))]

movies = pd.read_csv(
    os.path.join(DATA_DIR, 'u.item'),
    sep='|', names=movie_cols,
    encoding='latin-1', header=None
)
print(f"  ✅ {len(movies)} movies loaded!\n")

# ─── STEP 3: RATINGS ─────────────────────────────────────
print("Step 3: Ratings load kar raha hai...")
ratings = pd.read_csv(
    os.path.join(DATA_DIR, 'u.data'),
    sep='\t', names=['userId','movieId','rating','timestamp'],
    header=None
)
print(f"  ✅ {len(ratings):,} ratings | {ratings['userId'].nunique()} users\n")

# ─── STEP 4: GENRES COLUMNS ──────────────────────────────
print("Step 4: Genres column ban raha hai...")
g_cols = [f'g_{i}' for i in range(len(genre_names))]

def genres_str(row):
    g = [genre_names[i] for i,c in enumerate(g_cols) if row[c]==1]
    return ', '.join(g) if g else 'Unknown'

def genres_list(row):
    return [genre_names[i] for i,c in enumerate(g_cols) if row[c]==1]

movies['genres_display'] = movies.apply(genres_str, axis=1)
movies['genres_list']    = movies.apply(genres_list, axis=1)
print("  ✅ Done!\n")

# ─── STEP 5: YEAR + CLEAN TITLE ──────────────────────────
print("Step 5: Year + Clean title...")

def extract_year(t):
    m = re.search(r'\((\d{4})\)', str(t))
    return int(m.group(1)) if m else 0

def clean_title(t):
    return re.sub(r'\s*\(\d{4}\)\s*', '', str(t)).strip()

movies['year']        = movies['title'].apply(extract_year)
movies['title_clean'] = movies['title'].apply(clean_title)
print(f"  ✅ Year range: {movies[movies['year']>0]['year'].min()} – {movies[movies['year']>0]['year'].max()}\n")

# ─── STEP 6: RATINGS STATS MERGE ─────────────────────────
print("Step 6: Rating stats merge kar raha hai...")
stats = ratings.groupby('movieId').agg(
    avg_rating  = ('rating','mean'),
    num_ratings = ('rating','count')
).reset_index()
movies = movies.merge(stats, on='movieId', how='left')
movies['avg_rating']  = movies['avg_rating'].fillna(0).round(2)
movies['num_ratings'] = movies['num_ratings'].fillna(0).astype(int)
print("  ✅ Done!\n")

# ─── STEP 7: WEIGHTED POPULARITY ─────────────────────────
print("Step 7: Popularity score calculate ho raha hai...")
m_thresh = movies['num_ratings'].quantile(0.25)
C_avg    = movies['avg_rating'].mean()
def w_rating(row):
    v = row['num_ratings']; R = row['avg_rating']
    return (v/(v+m_thresh))*R + (m_thresh/(v+m_thresh))*C_avg
movies['popularity'] = movies.apply(w_rating, axis=1).round(4)
print(f"  ✅ Global avg rating: {C_avg:.2f}\n")

# ─── STEP 8: SOUP ────────────────────────────────────────
print("Step 8: Feature soup ban raha hai (TF-IDF ke liye)...")
def make_soup(row):
    g = ' '.join(row['genres_list'])
    t = row['title_clean'].lower()
    # Genre ko 3x weight, title bhi include
    return f"{g} {g} {g} {t}".strip()
movies['soup'] = movies.apply(make_soup, axis=1)
print("  ✅ Done!\n")

# ─── STEP 9: TF-IDF ──────────────────────────────────────
print("Step 9: TF-IDF Vectorization...")
tfidf = TfidfVectorizer(max_features=3000, stop_words='english', ngram_range=(1,2))
tfidf_matrix = tfidf.fit_transform(movies['soup'])
print(f"  ✅ Matrix shape: {tfidf_matrix.shape}\n")

# ─── STEP 10: COSINE SIMILARITY ──────────────────────────
print("Step 10: Cosine Similarity calculate ho rahi hai...")
similarity = cosine_similarity(tfidf_matrix, tfidf_matrix)
print(f"  ✅ Similarity Matrix: {similarity.shape}\n")

# ─── STEP 11: RATINGS PIVOT ──────────────────────────────
print("Step 11: User-Movie pivot matrix ban rahi hai...")
ratings_matrix = ratings.pivot_table(
    index='userId', columns='movieId', values='rating'
).fillna(0)
print(f"  ✅ Ratings Matrix: {ratings_matrix.shape}\n")

# ─── STEP 12: INDEX MAPPING ──────────────────────────────
print("Step 12: Title index mapping...")
movies = movies.reset_index(drop=True)
title_to_index = pd.Series(movies.index, index=movies['title_clean'].str.lower()).drop_duplicates()
title_orig_idx = pd.Series(movies.index, index=movies['title'].str.lower()).drop_duplicates()
print(f"  ✅ {len(title_to_index)} movies indexed!\n")

# ─── STEP 13: SAVE ALL ────────────────────────────────────
print("Step 13: Sab save ho raha hai...")
save_cols = ['movieId','title','title_clean','genres_display','genres_list',
             'year','avg_rating','num_ratings','popularity','imdb_url','soup']

movies[save_cols].to_csv(os.path.join(OUT_DIR,'movies_clean.csv'), index=True)
print("  ✅ movies_clean.csv saved!")

with open(os.path.join(MODEL_DIR,'similarity_matrix.pkl'),'wb') as f:
    pickle.dump(similarity, f)
print("  ✅ similarity_matrix.pkl saved!")

with open(os.path.join(MODEL_DIR,'movies_model.pkl'),'wb') as f:
    pickle.dump({'df':movies[save_cols],'title_to_index':title_to_index,'title_orig_idx':title_orig_idx}, f)
print("  ✅ movies_model.pkl saved!")

with open(os.path.join(MODEL_DIR,'ratings_matrix.pkl'),'wb') as f:
    pickle.dump(ratings_matrix, f)
print("  ✅ ratings_matrix.pkl saved!")

# ─── SUMMARY ─────────────────────────────────────────────
print("\n" + "="*60)
print("  ✅ PREPROCESSING COMPLETE!")
print("="*60)
print(f"  Movies    : {len(movies)}")
print(f"  Users     : {ratings['userId'].nunique()}")
print(f"  Ratings   : {len(ratings):,}")
print(f"  Genres    : {len(genre_names)}")
print(f"  Avg Rating: {C_avg:.2f} / 5.0")
print(f"\n  ▶️  Ab app.py chalao: python app.py")
print("="*60)