"""Content-addressed storage and independent review for package-label images."""

from __future__ import annotations

import os
from datetime import date
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import cv2
import numpy as np

from .models import PackagingSnapshotEvidence, ProductRecord

_IMAGE_FORMATS = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"RIFF", "image/webp", ".webp"),
)
_MIN_SHORT_EDGE = 480
_MIN_LONG_EDGE = 640
_MIN_CONTRAST_SCORE = 8.0
_MIN_SHARPNESS_SCORE = 20.0


class PackagingEvidenceStore:
    """Store immutable label images and verify them before a second review."""

    def __init__(self, root: str | Path, *, max_bytes: int = 20_000_000) -> None:
        self.root = Path(root)
        self.max_bytes = max_bytes

    def ingest(
        self,
        image_bytes: bytes,
        *,
        evidence_kind: str,
        artifact_type: str,
        source_url: str,
        captured_at: date,
        sku: str,
        specification: str,
        reviewer_id: str,
        allowed_hosts: set[str] | None = None,
    ) -> PackagingSnapshotEvidence:
        if not image_bytes or len(image_bytes) > self.max_bytes:
            raise ValueError("Packaging image is empty or exceeds the size limit")
        media_type, suffix = _detect_image_type(image_bytes)
        _validate_source(source_url, artifact_type, allowed_hosts)
        decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None or decoded.ndim != 3:
            raise ValueError("Packaging evidence is not a decodable image")
        height, width = decoded.shape[:2]
        sharpness_score, contrast_score = _image_quality(decoded)
        digest = sha256(image_bytes).hexdigest()
        relative_path = Path("sha256") / digest[:2] / f"{digest}{suffix}"
        destination = self.root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha256(destination.read_bytes()).hexdigest() != digest:
                raise ValueError("Existing packaging artifact failed integrity verification")
        else:
            temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as handle:
                    handle.write(image_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary.replace(destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
        snapshot_key = sha256(
            f"{digest}\0{sku}\0{evidence_kind}\0{artifact_type}".encode()
        ).hexdigest()[:24]
        return PackagingSnapshotEvidence(
            snapshot_id=f"packaging:{snapshot_key}",
            evidence_kind=evidence_kind,
            artifact_type=artifact_type,
            source_url=source_url,
            captured_at=captured_at,
            content_hash=f"sha256:{digest}",
            media_type=media_type,
            byte_size=len(image_bytes),
            pixel_width=width,
            pixel_height=height,
            sharpness_score=sharpness_score,
            contrast_score=contrast_score,
            artifact_path=relative_path.as_posix(),
            sku=sku,
            specification=specification,
            review_status="pending_second_review",
            primary_reviewer_id=reviewer_id,
        )

    def add_second_review(
        self,
        snapshot: PackagingSnapshotEvidence,
        *,
        reviewer_id: str,
        reviewed_at: date,
        approve: bool = True,
    ) -> PackagingSnapshotEvidence:
        if snapshot.review_status != "pending_second_review":
            raise ValueError("Only pending evidence can receive a second review")
        if reviewer_id == snapshot.primary_reviewer_id:
            raise ValueError("The second reviewer must be independent")
        if not self.verify_artifact(snapshot):
            raise ValueError("Packaging artifact changed after capture")
        return snapshot.model_copy(
            update={
                "secondary_reviewer_id": reviewer_id,
                "reviewed_at": reviewed_at,
                "review_status": "verified" if approve else "rejected",
            }
        )

    def verify_artifact(self, snapshot: PackagingSnapshotEvidence) -> bool:
        relative = Path(snapshot.artifact_path)
        if relative.is_absolute() or ".." in relative.parts:
            return False
        artifact = self.root / relative
        if not artifact.is_file():
            return False
        payload = artifact.read_bytes()
        return (
            len(payload) == snapshot.byte_size
            and f"sha256:{sha256(payload).hexdigest()}" == snapshot.content_hash
        )


def attach_verified_snapshot(
    product: ProductRecord, snapshot: PackagingSnapshotEvidence
) -> ProductRecord:
    """Bind reviewed evidence to its exact product and refresh the record hash."""

    if snapshot.review_status != "verified":
        raise ValueError("Only verified packaging evidence can be attached")
    if not product.sku or not product.specification:
        raise ValueError("Product SKU and specification are required")
    if snapshot.sku != product.sku or snapshot.specification != product.specification:
        raise ValueError("Packaging evidence SKU/specification does not match product")
    snapshots = {
        item.snapshot_id: item for item in product.label.packaging_snapshots
    }
    snapshots[snapshot.snapshot_id] = snapshot
    updated = product.model_copy(
        update={
            "label": product.label.model_copy(
                update={"packaging_snapshots": list(snapshots.values())}
            )
        }
    )
    from .evidence_audit import label_content_hash

    return updated.model_copy(
        update={
            "label": updated.label.model_copy(
                update={"content_hash": label_content_hash(updated)}
            )
        }
    )


def _detect_image_type(payload: bytes) -> tuple[str, str]:
    for magic, media_type, suffix in _IMAGE_FORMATS:
        if payload.startswith(magic):
            if media_type == "image/webp" and payload[8:12] != b"WEBP":
                continue
            return media_type, suffix
    raise ValueError("Only JPEG, PNG, and WebP packaging images are accepted")


def _image_quality(decoded: np.ndarray) -> tuple[float, float]:
    height, width = decoded.shape[:2]
    if min(height, width) < _MIN_SHORT_EDGE or max(height, width) < _MIN_LONG_EDGE:
        raise ValueError("Packaging evidence resolution is too low for label review")
    gray = cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY)
    contrast = float(gray.std())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if contrast < _MIN_CONTRAST_SCORE:
        raise ValueError("Packaging evidence has insufficient contrast")
    if sharpness < _MIN_SHARPNESS_SCORE:
        raise ValueError("Packaging evidence is too blurred for label review")
    return sharpness, contrast


def _validate_source(
    source_url: str, artifact_type: str, allowed_hosts: set[str] | None
) -> None:
    parsed = urlparse(source_url)
    if artifact_type == "packaging_photo" and parsed.scheme == "capture":
        return
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Evidence source must use HTTPS or a local capture URI")
    if allowed_hosts is not None and parsed.hostname.lower() not in {
        host.lower() for host in allowed_hosts
    }:
        raise ValueError("Evidence source host is not allowlisted")
