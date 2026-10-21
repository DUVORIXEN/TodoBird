"""
TODO BIRD — Media Management Service (Batch 3.5)
Safe, offline-first local media management:
- Collision-free filename management (UUID/hash based)
- Managed storage inside Todo Bird application data directory
- Automatic high-quality thumbnail generation
- Non-blocking, cached thumbnail & preview loading
- Corrupt/missing image error resilience
- Zero cloud/telemetry calls
"""
import os
import shutil
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from PySide6.QtGui import QImage, QPixmap, QImageReader
from PySide6.QtCore import Qt

from todo_bird_app.services.path_resolver import PathResolver

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".svg"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB safety limit
MAX_DIMENSION = 8192  # 8k dimension safety limit


class MediaService:
    """Manages application media assets, covers, backgrounds, and thumbnails."""

    _pixmap_cache: Dict[str, QPixmap] = {}

    @classmethod
    def get_base_media_dir(cls) -> Path:
        base = PathResolver.get_media_dir()
        base.mkdir(parents=True, exist_ok=True)
        return base

    @classmethod
    def get_category_dir(cls, category: str = "tasks") -> Path:
        valid_cat = "".join(c for c in category if c.isalnum() or c in ("_", "-")) or "tasks"
        cat_dir = cls.get_base_media_dir() / valid_cat
        cat_dir.mkdir(parents=True, exist_ok=True)
        return cat_dir

    @classmethod
    def get_thumbnails_dir(cls) -> Path:
        thumb_dir = cls.get_base_media_dir() / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        return thumb_dir

    @classmethod
    def import_media(
        cls,
        source_path: str,
        category: str = "tasks",
        db_manager: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Imports an image from a user-specified path into Todo Bird's managed media store.
        Returns a dict containing relative_path, thumbnail_path, width, height, file_size, etc.
        """
        if not source_path or not os.path.exists(source_path):
            logger.warning("Source image path does not exist: %s", source_path)
            return None

        src_p = Path(source_path).resolve()
        ext = src_p.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            logger.warning("Unsupported media extension: %s", ext)
            return None

        try:
            file_size = src_p.stat().st_size
            if file_size > MAX_FILE_SIZE_BYTES:
                logger.warning("Media file exceeds maximum size limit (50MB): %d bytes", file_size)
                return None

            # Verify image can be parsed by Qt
            reader = QImageReader(str(src_p))
            if not reader.canRead():
                logger.warning("Corrupt or unreadable image file: %s", source_path)
                return None

            orig_size = reader.size()
            width, height = orig_size.width(), orig_size.height()
            if width > MAX_DIMENSION or height > MAX_DIMENSION:
                logger.warning("Image dimensions exceed 8192px safety limit: (%d, %d)", width, height)
                return None

            # Generate collision-free destination filename
            unique_name = f"{uuid.uuid4().hex}{ext}"
            cat_dir = cls.get_category_dir(category)
            dest_p = cat_dir / unique_name

            # Copy file to managed store
            shutil.copy2(src_p, dest_p)

            # Generate thumbnail
            thumb_name = f"{dest_p.stem}_thumb.png"
            thumb_p = cls.get_thumbnails_dir() / thumb_name
            cls._generate_thumbnail(dest_p, thumb_p, max_size=192)

            relative_path = f"{category}/{unique_name}"
            rel_thumb_path = f"thumbnails/{thumb_name}" if thumb_p.exists() else ""

            meta = {
                "relative_path": relative_path,
                "thumbnail_path": rel_thumb_path,
                "width": width,
                "height": height,
                "file_size": file_size,
                "mime_type": f"image/{ext.lstrip('.')}",
            }

            if db_manager and hasattr(db_manager, "insert_media_asset"):
                try:
                    db_manager.insert_media_asset(
                        relative_path=relative_path,
                        asset_type=category,
                        thumbnail_path=rel_thumb_path,
                        mime_type=meta["mime_type"],
                        width=width,
                        height=height,
                        file_size=file_size,
                    )
                except Exception as e:
                    logger.warning("Failed to record media asset in DB: %s", e)

            return meta
        except Exception as exc:
            logger.error("Failed to import media file '%s': %s", source_path, exc, exc_info=True)
            return None

    @classmethod
    def _generate_thumbnail(cls, source_path: Path, thumb_path: Path, max_size: int = 192) -> bool:
        """Generates a high-quality, smoothed square/aspect-preserved thumbnail."""
        try:
            img = QImage(str(source_path))
            if img.isNull():
                return False
            scaled = img.scaled(
                max_size, max_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            return scaled.save(str(thumb_path), "PNG")
        except Exception as e:
            logger.warning("Failed to generate thumbnail for '%s': %s", source_path, e)
            return False

    @classmethod
    def get_absolute_path(cls, relative_or_abs_path: str) -> Optional[str]:
        """Resolves relative media path to an absolute path inside managed storage."""
        if not relative_or_abs_path:
            return None
        # If already absolute and exists, return it
        if os.path.isabs(relative_or_abs_path):
            return relative_or_abs_path if os.path.exists(relative_or_abs_path) else None

        managed_p = cls.get_base_media_dir() / relative_or_abs_path
        if managed_p.exists():
            return str(managed_p.resolve())
        return None

    @classmethod
    def get_thumbnail_path(cls, relative_or_abs_path: str) -> Optional[str]:
        """Returns the absolute path to the thumbnail if available, or original."""
        abs_orig = cls.get_absolute_path(relative_or_abs_path)
        if not abs_orig:
            return None
        orig_stem = Path(abs_orig).stem
        thumb_cand = cls.get_thumbnails_dir() / f"{orig_stem}_thumb.png"
        if thumb_cand.exists():
            return str(thumb_cand.resolve())
        return abs_orig

    @classmethod
    def load_pixmap(
        cls,
        relative_or_abs_path: str,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        use_thumbnail: bool = False,
    ) -> Optional[QPixmap]:
        """Loads a QPixmap safely with caching and optional size clamping."""
        if not relative_or_abs_path:
            return None

        target_path = cls.get_thumbnail_path(relative_or_abs_path) if use_thumbnail else cls.get_absolute_path(relative_or_abs_path)
        if not target_path or not os.path.exists(target_path):
            return None

        cache_key = f"{target_path}_{max_width}_{max_height}"
        if cache_key in cls._pixmap_cache:
            return cls._pixmap_cache[cache_key]

        try:
            pixmap = QPixmap(target_path)
            if pixmap.isNull():
                return None

            if max_width or max_height:
                w = max_width or pixmap.width()
                h = max_height or pixmap.height()
                pixmap = pixmap.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )

            cls._pixmap_cache[cache_key] = pixmap
            return pixmap
        except Exception as e:
            logger.warning("Error loading pixmap '%s': %s", target_path, e)
            return None

    @classmethod
    def delete_media(cls, relative_path: str) -> bool:
        """Deletes a managed media file and its corresponding thumbnail."""
        if not relative_path:
            return False
        abs_p = cls.get_absolute_path(relative_path)
        if not abs_p:
            return False
        try:
            p = Path(abs_p)
            if p.exists() and p.is_file():
                p.unlink()

            thumb_p = cls.get_thumbnails_dir() / f"{p.stem}_thumb.png"
            if thumb_p.exists() and thumb_p.is_file():
                thumb_p.unlink()

            # Evict from cache
            cls._pixmap_cache = {k: v for k, v in cls._pixmap_cache.items() if str(p) not in k}
            return True
        except Exception as e:
            logger.warning("Error deleting media file '%s': %s", abs_p, e)
            return False
