import os
from fastmcp import FastMCP,Context
from starlette.requests import Request
from starlette.responses import Response, JSONResponse, FileResponse, HTMLResponse
from config import settings
from utilities import dependencies
from pathlib import Path

def ensure_download_dir():
    if not os.path.exists(settings.DOWNLOAD_DIR):
        os.makedirs(settings.DOWNLOAD_DIR)
        return True
    return False

async def prepare_file_for_download(file_path: str, ctx: Context) -> Path:
    '''
    Prepares a file for download by copying it to the server's designated download directory.
    Validates the file path against allowed roots and checks for existence before copying.
    User can then access the file via the /files/{filename} endpoint.
    '''
    import shutil
    try:
        file_path: Path = await dependencies.validate_path(file_path, ctx, must_exist=True, expected_type='file')
    except ValueError as e:
        dependencies.logger.error(f"File {file_path} is not valid or accessible or not within allowed roots: {e}")
        raise

    destination = os.path.join(Path(settings.DOWNLOAD_DIR).resolve(), file_path.name)
    # check if destination file already exists in the download directory
    if not os.path.exists(destination):
        shutil.copy2(file_path, destination)

    return f"File {file_path.name} prepared for download. Access it at http://{settings.MCP_HOST}:{settings.MCP_PORT}/files/{file_path.name}"

def ft_register_routes(mcp: FastMCP):

    if ensure_download_dir():
        dependencies.logger.info(f"Created download directory at {settings.DOWNLOAD_DIR}")

    async def download_file(request: Request) -> Response:
        filename = request.path_params["filename"]
        file_path = os.path.join(settings.DOWNLOAD_DIR, filename)
        dependencies.logger.info(f"Received download request for file: {filename}")
        try:
            file_path: Path = dependencies.check_path(file_path, check_existence=True)
            if file_path.is_file():
                dependencies.logger.info(f"File {filename} is valid and ready for download.")
                return FileResponse(file_path, media_type='application/octet-stream', filename=filename)
        except ValueError as e:
            dependencies.logger.warning(f"File {filename} is not valid or accessible: {e}")
            return JSONResponse({"status": "error", "message": f"File {filename} is not accessible or does not exist."})
        
    async def list_files(request: Request) -> Response:
        # list with html tags
        files = []
        try:
            files = os.listdir(settings.DOWNLOAD_DIR)
            for idx, file in enumerate(files):
                file_path = os.path.join(settings.DOWNLOAD_DIR, file)
                try:
                    file_size = os.path.getsize(file_path)
                    files[idx] = f"<li><a href='/files/{file}'>{file}</a>({file_size} bytes)</li>"
                except OSError:
                    files[idx] = f"<li><a href='/files/{file}'>{file}</a>(unknown size)</li>"
        except Exception as e:
            dependencies.logger.error(f"Error listing files in download directory: {e}")
            return JSONResponse({"status": "error", "message": "Could not list files."})

        if not files:
            file_list_html = "<li>Empty directory</li>"
        else:
            file_list_html = "".join(files)

        html_content = f"""
        <html>
            <head><title>File Server</title></head>
            <body>
                <h1>📂 Available Files</h1>
                <ul>
                    {file_list_html}
                </ul>
            </body>
        </html>
        """
        return HTMLResponse(html_content)
    
    mcp.custom_route("/files/{filename}", methods=["GET"])(download_file)
    mcp.custom_route("/files", methods=["GET"])(list_files)
    mcp.tool("prepare_file_for_download")(prepare_file_for_download)
