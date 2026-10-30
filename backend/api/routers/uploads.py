import os
import shutil
import zipfile
from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlmodel import SQLModel
from pathlib import Path
from pydantic import BaseModel

from api.artifacts import redact_server_paths_bytes

# Create a router
# prefix: path prefix for every route below
# tags: labels used to group routes in Swagger UI
# responses: shared error responses
router = APIRouter(
    prefix="/api/uploads",
    tags=["uploads"],
)

class UploadPublic(SQLModel):
    message: str
    file_path: str

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 2. Create uploads relative to BASE_DIR
UPLOAD_DIR = BASE_DIR / "uploads"
CSV_DIR = UPLOAD_DIR / "csv"
IMAGE_DIR = UPLOAD_DIR / "image"
CSV_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/csv", response_model=UploadPublic)
async def upload_csv(file: UploadFile = File(...)):
    # 1. Check the file format (optional, for extra safety)
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files can be uploaded")

    # 2. Sanitise the filename: prevent path traversal
    safe_filename = os.path.basename(file.filename) 
    save_path = CSV_DIR / safe_filename

    try:
        # 3. Use shutil for the write so large files do not exhaust memory
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save the file: {str(e)}")
    finally:
        await file.close() # Close the file
    
    # 4. Return data matching the UploadPublic definition
    return {
        "message": f"File uploaded: {safe_filename}",
        "file_path": f"/uploads/csv/{safe_filename}"
    }

# Allowed image formats
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

@router.post("/image", response_model=UploadPublic)
async def upload_image(file: UploadFile = File(...)):
    # 1. Get the extension and check the format
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # 2. Sanitise the filename
    safe_filename = os.path.basename(file.filename)
    save_path = IMAGE_DIR / safe_filename

    try:
        # 3. Stream the file to disk
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save the image: {str(e)}")
    finally:
        await file.close()

    # 4. Return the formatted data
    return {
        "message": f"Image uploaded: {safe_filename}",
        # Matches the actual mount path and folder naming: uploads/image/...
        "file_path": f"/uploads/image/{safe_filename}",
    }


class ZipRequest(BaseModel):
    folder_name: str


# File extensions whose content is redacted when packing. This is an allowlist, not "exclude known binaries":
# analysis output contains binaries such as .qs (serialised R objects) and .png, and any byte-level
# rewrite of them can silently corrupt the content -- a broken chart gives no error, the physician just
# sees a file that will not open. Unknown extensions are always copied as is; missing one text format
# costs far less than destroying a result.
_REDACTED_SUFFIXES = {
    ".md", ".txt", ".js", ".json", ".html", ".htm", ".csv", ".tsv", ".log", ".r",
}


def _write_zip_with_redacted_text(src: Path, dest: Path) -> None:
    """Pack the contents of `src` into `dest`, redacting server path prefixes in text files.

    Replaces the original `shutil.make_archive`: that function can only copy verbatim, and the ZIP ships
    the files themselves without passing the `/api/artifacts` API boundary redaction, so physicians who
    unzipped and opened the report still saw `/home/<user>/projects/...` (measured 2026-08-12).

    The only behavioural difference from `make_archive` is that directory entries are no longer written
    (files only). Empty directories therefore do not appear in the ZIP; analysis output has no meaningful
    empty directories, and every unzip tool creates intermediate directories from the file paths.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            arcname = path.relative_to(src).as_posix()
            if path.suffix.lower() in _REDACTED_SUFFIXES:
                zf.writestr(arcname, redact_server_paths_bytes(path.read_bytes()))
            else:
                zf.write(path, arcname)


@router.post("/download-zip")
async def download_analysis_zip(req: ZipRequest):
    # 1. Get the absolute path of the project root
    BASE_DIR = os.path.abspath(".")
    
    # The frontend sends "uploads/output/id_mapping/2026-06-18-xx"
    # Convert it to an absolute (Windows) path
    target_folder_path = os.path.abspath(os.path.join(BASE_DIR, req.folder_name))
    
    # 2. Make sure it can only operate inside the project's uploads folder
    uploads_absolute_path = os.path.abspath(os.path.join(BASE_DIR, "uploads"))
    if not target_folder_path.startswith(uploads_absolute_path):
        raise HTTPException(status_code=400, detail="Invalid download path: outside the uploads folder")

    # 3. Check that the physical folder actually exists
    if not os.path.exists(target_folder_path):
        raise HTTPException(status_code=404, detail=f"Folder not found on the server. Expected path: {target_folder_path}")
        
    # 4. Parse the date to decide the zip's absolute path
    date_str = target_folder_path.replace("\\", "/").split("/")[-1] 
    
    OUTPUT_BASE = os.path.join(uploads_absolute_path, "output", "zip")
    os.makedirs(OUTPUT_BASE, exist_ok=True) 
    
    zip_output_base = os.path.join(OUTPUT_BASE, f"analysis_{date_str}")
    
    try:
        # 5. Run the compression, redacting server paths in text files along the way
        _write_zip_with_redacted_text(Path(target_folder_path),
                                      Path(f"{zip_output_base}.zip"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create the ZIP file: {str(e)}")
        
    # 6. Return the download URL to the frontend (matches app.mount("/uploads", ...) in main.py)
    return {
        "status": "success",
        "zip_url": f"/uploads/output/zip/analysis_{date_str}.zip",
        "filename": f"analysis_{date_str}.zip"
    }