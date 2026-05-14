# train_classifier.py
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline


def load_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.dropna(subset=["text", "label"], inplace=True)
    df["text"] = df["text"].astype(str)
    df["label"] = df["label"].astype(str)
    return df


def train_model(texts, labels):
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(stop_words="english")),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )
    model.fit(texts, labels)
    return model


def show_top_keywords(model, top_n: int = 20):
    tfidf = model.named_steps["tfidf"]
    clf = model.named_steps["clf"]

    feature_names = np.array(tfidf.get_feature_names_out())
    classes = clf.classes_

    print("\n=== Top keywords per class ===")

    # Binary case: coef_.shape = (1, n_features) and exactly 2 classes
    if clf.coef_.shape[0] == 1 and len(classes) == 2:
        coefs = clf.coef_[0]
        for i, class_label in enumerate(classes):
            if i == 1:
                # positive side => class 1
                top_ids = np.argsort(coefs)[-top_n:]
            else:
                # negative side => class 0
                top_ids = np.argsort(-coefs)[-top_n:]
            top_words = feature_names[top_ids]
            print(f"\nClass: {class_label}")
            print(", ".join(top_words))
    else:
        # Multiclass case: one row per class
        for class_idx, class_label in enumerate(classes):
            coefs = clf.coef_[class_idx]
            top_ids = np.argsort(coefs)[-top_n:]
            top_words = feature_names[top_ids]
            print(f"\nClass: {class_label}")
            print(", ".join(top_words))
            
def main():
    base_dir = Path(__file__).parent
    csv_path = base_dir / "emails.csv"

    if not csv_path.exists():
        print(f"emails.csv not found at {csv_path}")
        return

    df = load_data(csv_path)
    texts = df["text"].tolist()
    labels = df["label"].tolist()

    print(f"Loaded {len(df)} samples with {len(set(labels))} classes: {sorted(set(labels))}")

    model = train_model(texts, labels)

    # Sanity check
    preds = model.predict(texts)
    print("\n=== Training classification report (sanity check) ===")
    print(classification_report(labels, preds))

    # Important keywords (useful for subscription/hidden fee rules)
    show_top_keywords(model, top_n=20)

    # Save
    model_path = base_dir / "email_classifier.pkl"
    joblib.dump(model, model_path)
    print(f"\nSaved model to {model_path}")


if __name__ == "__main__":
    main()