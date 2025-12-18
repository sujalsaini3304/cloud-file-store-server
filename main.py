from fastapi import FastAPI, UploadFile, File, Form, HTTPException , Query
from datetime import datetime
import cloudinary.uploader
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi.responses import FileResponse 
from fastapi.staticfiles import StaticFiles


import cloudinary_config
from bson import ObjectId
from db import files_collection
from utils import compress_image, should_compress_image, should_compress_doc

app = FastAPI(title="Secure Cloud File Upload API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite
        "http://localhost:3000",  # CRA
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message":"Server is running",
        "status":200
    }




# Serving and mounting file
app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")

@app.get("/{full_path:path}")
async def serve_react_app(full_path: str = ""):
    # Check if the requested path is a file in dist
    file_path = os.path.join("dist", full_path)
    
    # If it's a file that exists, serve it
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Otherwise, serve index.html (for React Router)
    return FileResponse("dist/index.html")



@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    name: str = Form(...),
    type: str = Form(...),
    description: str = Form(None),
    tags: str = Form(None),
    size: int | None = Form(None),#optional
    user_email: str = Form(...)
):
    try:
        file_bytes = await file.read()

        # 🔥 Auto-calculate size
        calculated_size = len(file_bytes)

        # Use client size only if provided
        final_size = size if size else calculated_size

        # ---------- IMAGE ----------
        if file.content_type.startswith("image/"):
            if should_compress_image(calculated_size):
                file_bytes = compress_image(file_bytes)

            result = cloudinary.uploader.upload(
                file_bytes,
                folder=f"CloudFileStore/{user_email}/Images",
                resource_type="image"
            )

        # ---------- DOCUMENT ----------
        elif file.content_type in (
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain"
        ):
            result = cloudinary.uploader.upload(
                file_bytes,
                folder=f"CloudFileStore/{user_email}/Documents",
                resource_type="raw",
                transformation=[{"quality": "auto"}]
                if should_compress_doc(calculated_size)
                else None
            )

        else:
            raise HTTPException(400, "Unsupported file type")

        # ---------- METADATA ----------
        doc = {
            "name": name,
            "type": type,
            "description": description,
            "tags": tags.split(",") if tags else [],
            "original_size": calculated_size,   # backend truth
            "reported_size": size,              # frontend (optional)
            "final_size": len(file_bytes),      # after compression
            "user_email": user_email,
            "url": result["secure_url"],
            "public_id": result["public_id"],
            "uploaded_at": datetime.utcnow()
        }

        files_collection.insert_one(doc)

        return {
            "message": "File uploaded successfully",
            "file_url": result["secure_url"],
            "original_size": calculated_size,
            "final_size": len(file_bytes),
            "compressed": calculated_size != len(file_bytes)
        }

    except Exception as e:
        raise HTTPException(500, str(e))
    


# DELETE /files?user_email=test@gmail.com&file_id=665c21a4e8c98d44faedc101
# DELETE /files?user_email=test@gmail.com

@app.delete("/files")
async def delete_files(
    user_email: str = Query(..., description="User email"),
    file_id: str | None = Query(
        None,
        description="MongoDB _id of file (optional)"
    )
):
    # ---------- CASE 1: DELETE SINGLE FILE ----------
    if file_id:
        file_doc = files_collection.find_one({
            "_id": ObjectId(file_id),
            "user_email": user_email
        })

        if not file_doc:
            raise HTTPException(
                status_code=404,
                detail="File not found or access denied"
            )

        # Delete from Cloudinary
        cloudinary.uploader.destroy(
            file_doc["public_id"],
            resource_type="image" if file_doc["type"] == "image" else "raw"
        )

        # Delete from MongoDB
        files_collection.delete_one({"_id": ObjectId(file_id)})

        return {
            "message": "File deleted successfully",
            "file_id": file_id
        }

    # ---------- CASE 2: DELETE ALL FILES OF USER ----------
    files = list(files_collection.find({"user_email": user_email}))

    if not files:
        return {
            "message": "No files found for user",
            "deleted": 0
        }

    deleted_count = 0

    for file in files:
        cloudinary.uploader.destroy(
            file["public_id"],
            resource_type="image" if file["type"] == "image" else "raw"
        )
        deleted_count += 1

    files_collection.delete_many({"user_email": user_email})

    return {
        "message": "All user files deleted successfully",
        "deleted": deleted_count
    }

