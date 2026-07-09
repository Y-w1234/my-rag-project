@echo off
REM ============================================================
REM  数据库静态加密脚本 (Windows EFS)
REM
REM  原理: Windows Encrypting File System (EFS)
REM  - 使用你的 Windows 登录密码加密文件
REM  - 只有你的账户能解密，其他用户/进程无法读取
REM  - 对应用程序透明，SQLite 无需任何代码改动
REM  - 适用于 Windows 所有版本 (NTFS 分区)
REM
REM  验证加密状态: cipher /c data\rag_app.db
REM  解密 (如需):  cipher /d /s:data
REM ============================================================

echo ========================================
echo   数据库静态加密 (Windows EFS)
echo ========================================
echo.

echo [1/3] 加密 SQLite 数据库文件...
cipher /e "data\rag_app.db" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo    ✅ data\rag_app.db 已加密
) else (
    echo    ⚠️  data\rag_app.db 加密失败 (可能文件不存在)
)

cipher /e "data\app.db" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo    ✅ data\app.db 已加密
) else (
    echo    ⚠️  data\app.db 加密失败 (可能文件不存在)
)

echo.
echo [2/3] 加密 ChromaDB 向量库...
cipher /e "chroma_db\chroma.sqlite3" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo    ✅ chroma_db\chroma.sqlite3 已加密
) else (
    echo    ⚠️  chroma_db\chroma.sqlite3 加密失败 (可能文件不存在)
)

echo.
echo [3/3] 验证加密状态...
echo.
cipher /c "data\rag_app.db" 2>nul | findstr /C:"E" >nul
if %ERRORLEVEL% EQU 0 (
    echo    ✅ 加密中: data\rag_app.db
) else (
    echo    ➖ 未加密: data\rag_app.db (文件可能不存在)
)

cipher /c "chroma_db\chroma.sqlite3" 2>nul | findstr /C:"E" >nul
if %ERRORLEVEL% EQU 0 (
    echo    ✅ 加密中: chroma_db\chroma.sqlite3
) else (
    echo    ➖ 未加密: chroma_db\chroma.sqlite3 (文件可能不存在)
)

echo.
echo ========================================
echo   完成!
echo   加密后的文件在资源管理器中显示为绿色。
echo   应用程序无需任何修改，正常使用即可。
echo ========================================

pause
