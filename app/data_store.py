# app/data_store.py
from datetime import datetime, timedelta

IMAGES = []
base = datetime.utcnow() - timedelta(days=2)

for i in range(1, 51):
    IMAGES.append({
        "id": i,
        "owner": "alice" if i % 2 else "bob",
        "filename": f"img_{i}.png",
        "kind": ["original", "grayscale", "edge"][i % 3],
        "status": ["ready", "processing", "failed"][i % 3],
        "created_at": base + timedelta(minutes=i * 7),
    })
