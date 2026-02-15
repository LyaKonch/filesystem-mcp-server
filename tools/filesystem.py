from pathlib import Path
import shutil
from fastmcp import Context
from utilities import dependencies
from typing import List
import os
from utilities.filereader import FileReader
from utilities.imagereader import ImageReader

async def list_files(path: str, ctx: Context) -> str:
    """List files and directories at the given path."""
    try:
        target_path = await dependencies.validate_path(path, ctx, must_exist=True, expected_type='dir')
        
        items = []
        for item in target_path.iterdir():
            prefix = "📁" if item.is_dir() else "📄"
            items.append(f"{prefix} {item.name}")
            
        return "\n".join(sorted(items))
    except Exception as e:
        return f"Error: {str(e)}"


async def read_file(path: str, ctx: Context, include_images: bool = False):
    """
    Read file content.
    
    Args:
        path: Path to the file to read
        include_images: Whether to include image data in the result (Sample their description)
        BEWARE: Use with caution and only when necessary. 
        Its like adding images to the prompt, thus your limit can be reached very fast, especially with files containing many images.
        Also not every client supports sampling and not every model supports OCR/vision, therefore, if you need this tool, you should check those info beforehand.
    """
    try:
        target_path = await dependencies.validate_path(path, ctx, must_exist=True, expected_type='file')
        
        reader = None
        if include_images:
            if dependencies.checkSamplingCapability(ctx.session):
                reader = ImageReader()
            else:
                ctx.info("Client does not support sampling, cannot include image descriptions.")
                include_images = False
        
        result = FileReader([target_path], include_images=include_images).read()
        
        if result and len(result) > 0:
            file_data = result[0]
            file_content = file_data.get("content", {})
            
            # for docx files, file_content has "pages" key with list of page dicts
            if isinstance(file_content, dict) and "pages" in file_content:
                pages = file_content["pages"]
                
                # If include_images and reader is available, describe images
                if include_images and reader:
                    for page in pages:
                        for obj in page.get("media", []):
                            if obj["kind"] == "image":
                                try:
                                    image_b64 = obj["data"].get("bytes_b64", "")
                                    mime_type = obj["data"].get("mime_type", "image/png")
                                    if image_b64:
                                        description = await reader.describe_base64(image_b64, ctx, mime_type)
                                        obj["description"] = description
                                    obj["data"].pop("bytes_b64", None)
                                    #obj["data"].pop("sha1", None)
                                except Exception as e:
                                    dependencies.logger.warning(f"Failed to describe image {obj['id']}: {e}")
            
            return file_data
        
        return {"metadata": {}, "content": {}}
        
    except UnicodeDecodeError:
        return f"Error: File '{path}' contains binary data or unsupported encoding"
    except Exception as e:
        return f"Error reading file: {str(e)}"
    
async def write_file(path: str, content: str, ctx: Context) -> str:
    try:
        # for writing we need to check the path without existence check, because we might be creating a new file or overwrite
        target_path = await dependencies.validate_path(path, ctx, must_exist=False)

        if not await dependencies.withinAllowed(target_path.parent, ctx):
             return f"Error: Access denied to write in '{target_path.parent}'"
        # Create parent directories if they don't exist
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        target_path.write_text(content, encoding="utf-8")
        return f"Saved to {target_path}"
        
    except Exception as e:
        return f"Error: {e}"

async def create_directory(path: str, ctx: Context) -> str:
    """Create a new directory."""
    try:
        target_path = await dependencies.validate_path(path, ctx, must_exist=False)
        if not await dependencies.withinAllowed(target_path.parent, ctx):
             return f"Error: Access denied to create directory in '{target_path.parent}'"    
        target_path.mkdir(parents=True, exist_ok=True)
        return f"Created directory '{path}'"
    except Exception as e:
        return f"Error: {str(e)}"

async def list_directory_with_sizes(path: str, sort_by: str = "name", ctx: Context = None) -> str:
    """Get a detailed listing of files and directories with sizes.
    
    Args:
        path: Path to list contents of
        sort_by: Sort by 'name' or 'size' (default: name)
    """
    try:
        target_path = await dependencies.validate_path(path, ctx, must_exist=True, expected_type='dir')
        
        entries = []
        total_size = 0
        total_files = 0
        total_dirs = 0
        
        for item in target_path.iterdir():
            try:
                stats = item.stat()
                size = stats.st_size
                is_dir = item.is_dir()
                
                if is_dir:
                    total_dirs += 1
                    size_str = ""
                else:
                    total_files += 1
                    total_size += size
                    size_str = dependencies.format_size(size)
                
                entries.append({
                    'name': item.name,
                    'is_dir': is_dir,
                    'size': size,
                    'size_str': size_str
                })
            except Exception:
                # Skip files we can't stat
                continue
        
        # Sort entries
        if sort_by == "size":
            entries.sort(key=lambda x: x['size'], reverse=True)
        else:
            entries.sort(key=lambda x: x['name'].lower())
        
        # Format output
        lines = [f"Contents of '{path}':\n"]
        for entry in entries:
            prefix = "📁" if entry['is_dir'] else "📄"
            name = f"{entry['name']}/" if entry['is_dir'] else entry['name']
            size = entry['size_str'].rjust(10) if entry['size_str'] else ""
            lines.append(f"{prefix} {name:<30} {size}")
        
        # Add summary
        lines.append("")
        lines.append(f"Total: {total_files} files, {total_dirs} directories")
        lines.append(f"Combined size: {dependencies.format_size(total_size)}")
        
        return "\n".join(lines)
    
    except Exception as e:
        return f"Error: {str(e)}"

async def analyze_directory_security(path: str, ctx: Context) -> str:
    """
    Provides comprehensive security and content analysis of a directory.
    
    Analyzes file types, potential security risks, content overview,
    and provides intelligent assessment using AI sampling if available.
    
    Args:
        path: Directory path to analyze
        ctx: MCP context for security validation and AI capabilities
    """
    try:
        import hashlib
        import mimetypes
        from datetime import datetime, timedelta
        from collections import defaultdict
        
        target_path = await dependencies.validate_path(path, ctx, must_exist=True, expected_type='dir')
        
        # Enhanced data collection
        file_types = {}
        mime_types = defaultdict(int)
        suspicious_files = []
        executable_files = []
        large_files = []
        hidden_files = []
        duplicate_files = defaultdict(list)  # hash -> [files]
        recent_files = []  # Modified in last 7 days
        old_files = []     # Not modified in last year
        empty_files = []
        
        # Time analysis
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        year_ago = now - timedelta(days=365)
        
        # Directory structure analysis
        depth_stats = defaultdict(int)
        dir_file_counts = defaultdict(int)
        
        # Security patterns
        suspicious_patterns = {
            'password': [],
            'key': [],
            'token': [],
            'secret': [],
            'credential': []
        }
        
        total_size = 0
        total_files = 0
        total_dirs = 0
        sample_files = []
        
        # Known suspicious extensions and patterns
        suspicious_extensions = {'.exe', '.scr', '.bat', '.cmd', '.com', '.pif', '.vbs', '.ps1', '.jar', '.app', '.dmg'}
        executable_extensions = {'.exe', '.msi', '.deb', '.rpm', '.app', '.dmg', '.run', '.sh', '.bat', '.cmd', '.ps1'}
        archive_extensions = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'}
        
        dependencies.logger.info(f"Starting comprehensive analysis of {target_path}")
        
        for root, dirs, files in os.walk(target_path):
            current_depth = len(Path(root).relative_to(target_path).parts)
            depth_stats[current_depth] += 1
            total_dirs += len(dirs)
            dir_file_counts[len(files)] += 1
            
            for file in files:
                file_path = Path(root) / file
                try:
                    file_stat = file_path.stat()
                    file_size = file_stat.st_size
                    total_size += file_size
                    total_files += 1
                    
                    # Basic file analysis
                    ext = file_path.suffix.lower()
                    file_types[ext] = file_types.get(ext, 0) + 1
                    
                    # MIME type analysis
                    mime_type, _ = mimetypes.guess_type(str(file_path))
                    if mime_type:
                        mime_types[mime_type] += 1
                    
                    # Time analysis
                    mod_time = datetime.fromtimestamp(file_stat.st_mtime)
                    if mod_time > week_ago:
                        recent_files.append(f"{file_path.name} ({mod_time.strftime('%Y-%m-%d')})")
                    elif mod_time < year_ago:
                        old_files.append(f"{file_path.name} ({mod_time.strftime('%Y-%m-%d')})")
                    
                    # Size analysis
                    if file_size == 0:
                        empty_files.append(str(file_path))
                    elif file_size > 100 * 1024 * 1024:  # >100MB
                        large_files.append(f"{file_path.name} ({dependencies.format_size(file_size)})")
                    
                    # Security analysis
                    if ext in suspicious_extensions:
                        suspicious_files.append(str(file_path))
                    
                    if ext in executable_extensions:
                        executable_files.append(str(file_path))
                    
                    if file.startswith('.'):
                        hidden_files.append(str(file_path))
                    
                    # Check for suspicious patterns in filename
                    filename_lower = file.lower()
                    for pattern in suspicious_patterns:
                        if pattern in filename_lower:
                            suspicious_patterns[pattern].append(str(file_path))
                    
                    # Duplicate detection (for files < 50MB to avoid memory issues)
                    if file_size < 50 * 1024 * 1024 and file_size > 0:
                        try:
                            with open(file_path, 'rb') as f:
                                file_hash = hashlib.sha256(f.read()).hexdigest()
                                duplicate_files[file_hash].append(str(file_path))
                        except:
                            pass
                    
                    # Content sampling for analysis
                    if len(sample_files) < 15 and ext in {'.txt', '.py', '.js', '.html', '.css', '.md', '.json', '.xml', '.yml', '.yaml', '.log', '.cfg', '.ini'}:
                        try:
                            if file_size < 50000:  # Only smaller files
                                content = file_path.read_text(encoding='utf-8', errors='ignore')[:1000]
                                sample_files.append(f"[{ext}] {file_path.name}: {content[:150]}...")
                        except:
                            pass
                            
                except (OSError, PermissionError, UnicodeDecodeError):
                    continue
        
        # Find actual duplicates (files with same hash but different paths)
        actual_duplicates = {h: files for h, files in duplicate_files.items() if len(files) > 1}
        
        # Generate comprehensive analysis
        analysis_parts = []
        analysis_parts.append(f"📁 COMPREHENSIVE DIRECTORY ANALYSIS: {path}")
        analysis_parts.append(f"📊 Files: {total_files:,} | Directories: {total_dirs:,} | Size: {dependencies.format_size(total_size)}")
        analysis_parts.append("")
        
        # File types analysis (top 10)
        analysis_parts.append("📋 FILE TYPES (Top 10):")
        sorted_types = sorted(file_types.items(), key=lambda x: x[1], reverse=True)
        for ext, count in sorted_types[:10]:
            ext_display = ext if ext else "(no extension)"
            percentage = (count / total_files) * 100
            analysis_parts.append(f"  {ext_display}: {count:,} ({percentage:.1f}%)")
        
        # MIME types analysis (top 5)
        if mime_types:
            analysis_parts.append("\n🎭 MIME TYPES (Top 5):")
            sorted_mimes = sorted(mime_types.items(), key=lambda x: x[1], reverse=True)
            for mime, count in sorted_mimes[:5]:
                analysis_parts.append(f"  {mime}: {count:,}")
        
        # Time analysis
        analysis_parts.append(f"\n⏰ TIME ANALYSIS:")
        analysis_parts.append(f"Recent files (last 7 days): {len(recent_files)}")
        analysis_parts.append(f"Old files (>1 year): {len(old_files)}")
        
        # Structure analysis
        max_depth = max(depth_stats.keys()) if depth_stats else 0
        analysis_parts.append(f"\n🏗️ STRUCTURE:")
        analysis_parts.append(f"Maximum depth: {max_depth} levels")
        analysis_parts.append(f"Empty files: {len(empty_files)}")
        
        # Duplicates analysis
        if actual_duplicates:
            total_duplicate_files = sum(len(files) for files in actual_duplicates.values())
            duplicate_waste = sum(
                file_types.get(Path(files[0]).suffix.lower(), 0) * len(files) 
                for files in actual_duplicates.values()
            )
            analysis_parts.append(f"🔄 Duplicates: {len(actual_duplicates)} sets, {total_duplicate_files} files")
        
        # Enhanced security assessment
        analysis_parts.append("\n🔒 ENHANCED SECURITY ASSESSMENT:")
        
        security_score = 100
        concerns = []
        
        # Threat scoring
        if suspicious_files:
            threat_score = min(40, len(suspicious_files) * 2)
            security_score -= threat_score
            concerns.append(f"⚠️  {len(suspicious_files)} potentially suspicious files")
            
        if executable_files:
            exec_score = min(25, len(executable_files))
            security_score -= exec_score
            concerns.append(f"🔧 {len(executable_files)} executable files")
            
        if len(hidden_files) > 20:
            security_score -= 20
            concerns.append(f"👁️  Many hidden files ({len(hidden_files)})")
            
        # Pattern-based threats
        pattern_threats = sum(len(files) for files in suspicious_patterns.values())
        if pattern_threats > 0:
            security_score -= min(15, pattern_threats)
            concerns.append(f"🔍 {pattern_threats} files with suspicious naming patterns")
            
        # Size-based concerns
        if total_size > 50 * 1024 * 1024 * 1024:  # >50GB
            concerns.append(f"📦 Very large directory ({dependencies.format_size(total_size)})")
        
        # Old file concern
        if len(old_files) > total_files * 0.5:
            concerns.append(f"�️  Many old files ({len(old_files)}) - potential cleanup needed")
        
        analysis_parts.append(f"Security Score: {max(0, security_score)}/100")
        
        if concerns:
            analysis_parts.append("Identified Concerns:")
            for concern in concerns:
                analysis_parts.append(f"  • {concern}")
        else:
            analysis_parts.append("✅ No major security concerns detected")
        
        # Detailed findings
        if suspicious_files[:3]:
            analysis_parts.append(f"\n🚨 SUSPICIOUS FILES (showing 3/{len(suspicious_files)}):")
            for file in suspicious_files[:3]:
                analysis_parts.append(f"  • {Path(file).name}")
        
        if any(suspicious_patterns.values()):
            analysis_parts.append("\n� SUSPICIOUS NAMING PATTERNS:")
            for pattern, files in suspicious_patterns.items():
                if files:
                    analysis_parts.append(f"  {pattern.upper()}: {len(files)} files")
        
        if actual_duplicates:
            analysis_parts.append(f"\n🔄 DUPLICATE ANALYSIS (showing 3/{len(actual_duplicates)}):")
            for i, (hash_val, files) in enumerate(list(actual_duplicates.items())[:3]):
                analysis_parts.append(f"  Set {i+1}: {len(files)} identical files")
                for file in files[:2]:  # Show first 2 of each set
                    analysis_parts.append(f"    • {Path(file).name}")
        
        if recent_files[:5]:
            analysis_parts.append(f"\n🆕 RECENT ACTIVITY (showing 5/{len(recent_files)}):")
            for file in recent_files[:5]:
                analysis_parts.append(f"  • {file}")
        
        basic_analysis = "\n".join(analysis_parts)
        
        # Enhanced AI analysis with more context
        try:
            from mcp.types import ClientCapabilities, SamplingCapability
            sampling_cap = ClientCapabilities(sampling=SamplingCapability())
            supports_sampling = ctx.session.check_client_capability(sampling_cap)
            
            if supports_sampling and sample_files:
                analysis_prompt = f"""Analyze this directory comprehensively:

                    STATISTICS:
                    - {total_files:,} files, {total_dirs:,} directories, {dependencies.format_size(total_size)}
                    - Top types: {', '.join([f"{ext}({count})" for ext, count in sorted_types[:5]])}
                    - Security score: {max(0, security_score)}/100
                    - {len(recent_files)} recent files, {len(old_files)} old files
                    - {len(actual_duplicates)} duplicate sets, {len(empty_files)} empty files

                    SAMPLE CONTENT:
                    {chr(10).join(sample_files[:8])}

                    SECURITY CONCERNS:
                    {chr(10).join(concerns) if concerns else "None detected"}

                    SUSPICIOUS PATTERNS:
                    {chr(10).join([f"{k}: {len(v)}" for k, v in suspicious_patterns.items() if v])}

                    Provide intelligent analysis covering:
                    1. Directory purpose/type identification
                    2. Development/project assessment  
                    3. Security risk evaluation
                    4. Cleanup/optimization recommendations
                    5. Data organization insights
                    6. Overall risk level (Low/Medium/High/Critical)

                    Be specific, actionable, under 300 words."""

                try:
                    ai_response = await ctx.sample(
                        analysis_prompt,
                        temperature=0.2,  # Lower temperature for factual analysis
                        max_tokens=400
                    )
                    
                    return f"{basic_analysis}\n\n🤖 AI COMPREHENSIVE ANALYSIS:\n{str(ai_response)}"
                    
                except Exception as e:
                    dependencies.logger.warning(f"AI analysis failed: {e}")
                    
        except Exception as e:
            dependencies.logger.warning(f"Error checking sampling capability: {e}")
        
        return basic_analysis
        
    except Exception as e:
        return f"Error analyzing directory: {str(e)}"

async def get_file_info(path: str, ctx: Context) -> str:
    """Get detailed metadata about a file or directory.
    
    Args:
        path: Path to the file or directory
    """
    try:
        target_path = dependencies.check_path(Path(path))
        
        if not dependencies.withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        if not target_path.exists():
            return f"Error: Path '{path}' does not exist"
        
        stats = target_path.stat()
        
        info = [
            f"Path: {target_path}",
            f"Name: {target_path.name}",
            f"Type: {'Directory' if target_path.is_dir() else 'File'}",
            f"Size: {dependencies.format_size(stats.st_size)}",
            f"Modified: {dependencies.format_timestamp(stats.st_mtime)}",
            f"Created: {dependencies.format_timestamp(stats.st_birthtime)}",
            f"Permissions: {oct(stats.st_mode)[-3:]}",
        ]
        
        if target_path.is_file():
            # Add file-specific info
            try:
                with open(target_path, 'rb') as f:
                    first_bytes = f.read(100)
                    is_binary = b'\x00' in first_bytes
                info.append(f"Binary: {'Yes' if is_binary else 'No'}")
                
                if not is_binary and target_path.suffix:
                    info.append(f"Extension: {target_path.suffix}")
                    
            except Exception:
                pass
        
        elif target_path.is_dir():
            # Add directory-specific info
            try:
                item_count = len(list(target_path.iterdir()))
                info.append(f"Items: {item_count}")
            except Exception:
                pass
        
        return "\n".join(info)
    
    except Exception as e:
        return f"Error: {str(e)}"


async def move_file(source: str, destination: str, ctx: Context) -> str:
    """Move or rename files and directories.
    
    Args:
        source: Source path
        destination: Destination path
    """
    try:
        source_path = dependencies.check_path(Path(source))
        dest_path = dependencies.check_path(Path(destination))
        
        if not dependencies.withinAllowed(source_path, ctx):
            return f"Error: Source path '{source}' is not within allowed roots"
        
        if not dependencies.withinAllowed(dest_path, ctx):
            return f"Error: Destination path '{destination}' is not within allowed roots"
        
        if not source_path.exists():
            return f"Error: Source '{source}' does not exist"
        
        if dest_path.exists():
            return f"Error: Destination '{destination}' already exists"
        
        # Create parent directories if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        source_path.rename(dest_path)
        return f"Successfully moved '{source}' to '{destination}'"
    
    except Exception as e:
        return f"Error moving file: {str(e)}"


async def search_files(path: str, pattern: str, ctx: Context, exclude_patterns: List[str] = None) -> str:
    """Search for files matching a pattern.
    
    Args:
        path: Directory to search in
        pattern: Glob pattern to match (e.g., '*.py', '**/*.txt')
        exclude_patterns: Optional list of patterns to exclude
    """
    try:
        
        search_path = await dependencies.validate_path(path, ctx, must_exist=True, expected_type='dir')
        
        if exclude_patterns is None or exclude_patterns == []:
            exclude_patterns = []
        
        matches = []
        
        # Use ** for recursive search
        glob_iter = search_path.rglob(pattern.replace('**/', '')) if '**' in pattern else search_path.glob(pattern)

        for file_path in glob_iter:
            if dependencies.should_include_file(file_path, search_path, exclude_patterns):
                matches.append(str(file_path))

        if not matches:
            return f"No files found matching pattern '{pattern}' in '{path}'"
        
        matches.sort()
        result = f"Found {len(matches)} files matching '{pattern}':\n"
        result += "\n".join(matches)
        return result
    
    except Exception as e:
        return f"Error searching files: {str(e)}"

async def read_multiple_files(paths: List[str], ctx: Context) -> str:
    """Read contents of multiple files simultaneously.
    
    Args:
        paths: List of file paths to read
    """
    try:
        if not paths:
            return "Error: No file paths provided"
        
        results = []
        
        for file_path in paths:
            try:
                # this ensures no loop stopping when one file is not accessible,
                #  and also provides individual error messages for each file
                target_path = dependencies.check_path(file_path, check_existence=True)
                
                if not dependencies.withinAllowed(target_path, ctx):
                    results.append(f"{file_path}: Error - Path not within allowed roots")
                    continue
                
                if not target_path.is_file():
                    results.append(f"{file_path}: Error - Not a file")
                    continue
                
                content = target_path.read_text(encoding='utf-8')
                results.append(f"{file_path}:\n{content}")
                
            except UnicodeDecodeError:
                results.append(f"{file_path}: Error - Binary file or unsupported encoding")
            except Exception as e:
                results.append(f"{file_path}: Error - {str(e)}")
        
        return "\n---\n".join(results)
    
    except Exception as e:
        return f"Error reading multiple files: {str(e)}"

async def delete_file(path: str, ctx: Context, confirm: bool = False) -> str:
    """Delete a file.
    
    Args:
        path: Path to the file to delete
    """
    try:
        target_path = await dependencies.validate_path(path, ctx, must_exist=True, expected_type='file')

        if not confirm:
            supports_elicitation = False
            try:
                supports_elicitation = dependencies.checkElicitationCapability(ctx.session)
            except:
                pass
            if supports_elicitation:
                try:
                    # this calls windows on the client side, asking user for confirmation
                    user_agreed = await ctx.elicit(
                        f"Are you sure you want to delete '{path}'? ", 
                        response_type=bool
                    )
                    if user_agreed:
                        # delete recursively
                        target_path.unlink()
                        return f"Successfully deleted file '{path}' via elicitation"
                    else:
                        return "Cancelled by user."
                except:
                    pass 

            # fallback message
            return (
                "⚠️To delete it, you must explicitely confirm.\n"
                "Please ask the user for permission, then call this tool again with `confirm=True` and try again."
            )   
    except Exception as e:
        return f"Error deleting file: {str(e)}"

async def delete_directory(path: str, confirm: bool = False, ctx: Context = None) -> str:
    """
    Delete a directory.
    Args:
        path: Path to delete
        confirm: Set to True to force deletion of non-empty directories.
    """
    target_path = await dependencies.validate_path(path, ctx, must_exist=True, expected_type='dir')

    if not confirm:
        supports_elicitation = False
        try:
            supports_elicitation = dependencies.checkElicitationCapability(ctx.session)
        except:
            pass

        if supports_elicitation:
            try:
                # this calls windows on the client side, asking user for confirmation
                user_agreed = await ctx.elicit(
                    f"Are you sure you want to delete '{path}'? ", 
                    response_type=bool
                )
                if user_agreed:
                    # delete recursively
                    shutil.rmtree(target_path)
                    return "Deleted via elicitation."
                else:
                    return "Cancelled by user."
            except:
                pass 

        # fallback message
        return (
            "⚠️To delete it, you must explicitely confirm.\n"
            "Please ask the user for permission, then call this tool again with `confirm=True` and try again."
        )

    shutil.rmtree(target_path)
    return f"Successfully deleted '{path}' (Confirmed)."

async def filesystem_summary(path: str, ctx: Context) -> dict:
    """
    Provides a summary of the filesystem at a given path.
    
    Args:
        path: The root path for the summary.
    """
    target_path = await dependencies.validate_path(path, ctx, must_exist=True, expected_type='dir')

    total_size = 0
    num_files = 0
    num_dirs = 0

    for dirpath, dirnames, filenames in os.walk(target_path):
        num_dirs += len(dirnames)
        num_files += len(filenames)
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)

    return {
        "path": str(target_path),
        "total_size": dependencies.format_size(total_size),
        "files": num_files,
        "directories": num_dirs,
    }

async def get_creative_file_description(path: str, ctx: Context) -> str:
    """
    Generates a creative, imaginative description of a file's contents.
    Uses sampling for more creative responses if the feature is supported.
    """
    # First read the file content directly
    try:
        target_path = await dependencies.validate_path(path, ctx, must_exist=True, expected_type='file')
        content = target_path.read_text(encoding='utf-8')
        content_summary = f"File: {path}\nContent preview: {content[:1000]}..." if len(content) > 1000 else f"File: {path}\nContent: {content}"
    except UnicodeDecodeError:
        return f"Error: File '{path}' contains binary data or unsupported encoding"
    except Exception as e:
        return f"Error reading file: {str(e)}"
    
    # Check if client supports sampling
    try:
        if dependencies.checkSamplingCapability(ctx.session):
            try:
                # Use sampling with higher temperature for more creative responses
                response = await ctx.sample(
                    f"Based on this content, write a creative summary of what this file represents. Imagine you are a detective trying to guess what information is for, be laconic but informative\n\n{content_summary}",
                    temperature=0.9,
                    max_tokens=300
                )
                return str(response)
            except Exception as e:
                dependencies.logger.warning(f"Sampling failed: {e}")
                # Fallback if sampling fails
                pass
    except Exception as e:
        dependencies.logger.warning(f"Error checking sampling capability: {e}")
    
    # Default response without sampling
    return f"Analysis of file content:\n\n{content_summary}"


def register(mcp):
    # group registration with the tag "filesystem"
    # read operations
    mcp.tool(tags=["filesystem", "read"])(list_files)
    mcp.tool(tags=["filesystem", "read"])(read_file)
    mcp.tool(tags=["filesystem", "read"])(read_multiple_files)
    mcp.tool(tags=["filesystem", "read"])(list_directory_with_sizes)
    mcp.tool(tags=["filesystem", "read"])(search_files)
    mcp.tool(tags=["filesystem", "read", "analysis"])(analyze_directory_security)
    mcp.tool(tags=["filesystem", "read", "creative"])(get_creative_file_description)
    mcp.tool(tags=["filesystem", "read", "summary"])(filesystem_summary)
    
    # write operations
    mcp.tool(tags=["filesystem", "write", "dangerous"])(write_file)
    mcp.tool(tags=["filesystem", "write"])(create_directory)
    mcp.tool(tags=["filesystem", "write"])(move_file)
    mcp.tool(tags=["filesystem", "write", "dangerous"])(delete_file)
    mcp.tool(tags=["filesystem", "write", "dangerous"])(delete_directory)