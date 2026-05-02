"""
Antrenare Random Forest pentru detecția atacurilor EDoS.
Rulează: python training/train_rf.py
Ieșiri:
  - training/models/rf_detector.pkl
  - training/models/rf_evaluation.png
"""
import numpy as np
import pandas as pd
import joblib
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score,
    precision_score, recall_score, f1_score
)

# ---------- Citire date ----------
print("=== Citire date ===")
df = pd.read_csv('training/data/edos_features.csv')
print(f"Total ferestre: {len(df)}")

# Features și labels
FEATURE_COLS = ['req_rate', 'unique_sources', 'ip_entropy', 'reg_ratio',
                'pdu_setup_ratio', 'pdu_release_ratio', 'mean_session_duration']
X = df[FEATURE_COLS].values
y = df['label'].values

print(f"Features: {FEATURE_COLS}")
print(f"Distribuție clase: legitim={sum(y==0)}, atac={sum(y==1)}")

# ---------- Împărțire train/test ----------
print("\n=== Împărțire train/test (80/20) ===")
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"Train: {len(X_train)}, Test: {len(X_test)}")

# ---------- Cross-validation pe setul de antrenare ----------
print("\n=== 5-fold cross-validation ===")
rf_cv = RandomForestClassifier(
    n_estimators=100,
    max_depth=10,
    random_state=42,
    n_jobs=-1
)
cv_scores = cross_val_score(rf_cv, X_train, y_train, cv=5, scoring='f1')
print(f"CV F1-score: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
print(f"CV scores per fold: {cv_scores}")

# ---------- Antrenare model final ----------
print("\n=== Antrenare model final ===")
rf = RandomForestClassifier(
    n_estimators=100,
    max_depth=10,
    random_state=42,
    n_jobs=-1
)
rf.fit(X_train, y_train)
print("Antrenare completă.")

# ---------- Evaluare pe test ----------
print("\n=== Evaluare pe set de test ===")
y_pred = rf.predict(X_test)

print(f"\nAcuratețe: {accuracy_score(y_test, y_pred):.3f}")
print(f"Precizie:  {precision_score(y_test, y_pred):.3f}")
print(f"Recall:    {recall_score(y_test, y_pred):.3f}")
print(f"F1-score:  {f1_score(y_test, y_pred):.3f}")

print("\nMatrice de confuzie:")
cm = confusion_matrix(y_test, y_pred)
print(f"             Pred Legitim  Pred Atac")
print(f"Real Legitim    {cm[0,0]:5d}      {cm[0,1]:5d}")
print(f"Real Atac       {cm[1,0]:5d}      {cm[1,1]:5d}")

print("\nClassification Report:")
print(classification_report(y_test, y_pred, target_names=['Legitim', 'Atac']))

# ---------- Importanța features ----------
print("\n=== Importanța features (Gini) ===")
importances = rf.feature_importances_
indices = np.argsort(importances)[::-1]
for i in indices:
    print(f"  {FEATURE_COLS[i]:25s}: {importances[i]:.3f}")

# ---------- Timpul de inferență ----------
import time
print("\n=== Timpul de inferență ===")
start = time.perf_counter()
for _ in range(1000):
    rf.predict(X_test[:1])
elapsed = (time.perf_counter() - start) / 1000 * 1000  # ms per inferență
print(f"Inferență per fereastră: {elapsed:.3f} ms")

# ---------- Salvare model ----------
print("\n=== Salvare model ===")
joblib.dump(rf, 'training/models/rf_detector.pkl')
joblib.dump(FEATURE_COLS, 'training/models/rf_features.pkl')
print("Model salvat: training/models/rf_detector.pkl")

# ---------- Vizualizare ----------
print("\n=== Generare grafice ===")
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 1. Matrice de confuzie
ax = axes[0]
im = ax.imshow(cm, cmap='Blues')
ax.set_xticks([0, 1])
ax.set_yticks([0, 1])
ax.set_xticklabels(['Legitim', 'Atac'])
ax.set_yticklabels(['Legitim', 'Atac'])
ax.set_xlabel('Predicție')
ax.set_ylabel('Realitate')
ax.set_title('Matrice de confuzie')
for i in range(2):
    for j in range(2):
        ax.text(j, i, str(cm[i, j]), ha='center', va='center',
                color='white' if cm[i, j] > cm.max() / 2 else 'black',
                fontsize=14, fontweight='bold')

# 2. Importanța features
ax = axes[1]
sorted_idx = np.argsort(importances)
ax.barh(range(len(sorted_idx)), importances[sorted_idx], color='#1D9E75')
ax.set_yticks(range(len(sorted_idx)))
ax.set_yticklabels([FEATURE_COLS[i] for i in sorted_idx])
ax.set_xlabel('Importanță (Gini)')
ax.set_title('Importanța features')
ax.grid(True, alpha=0.3, axis='x')

plt.tight_layout()
plt.savefig('training/models/rf_evaluation.png', dpi=100, bbox_inches='tight')
print("Grafic salvat: training/models/rf_evaluation.png")

print("\n=== TERMINAT ===")