#!/usr/bin/env bash
# ==============================================================================
# Antigravity CLI Metapackage Installer
# Installs extensions, agents, and skills into Antigravity CLI and Gemini CLI
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_EXT_DIR="${HOME}/.gemini/extensions"
TARGET_PLUGIN_DIR="${HOME}/.gemini/antigravity-cli/plugins"
TARGET_SKILLS_DIR="${HOME}/.agents/skills"

echo "🚀 Installing Antigravity CLI Extensions, Agents & Skills..."

# Ensure target directories exist
mkdir -p "${TARGET_EXT_DIR}"
mkdir -p "${TARGET_PLUGIN_DIR}"
mkdir -p "${TARGET_SKILLS_DIR}"

# Function to install an extension
install_extension() {
    local ext_name="$1"
    local ext_source="${SCRIPT_DIR}/extensions/${ext_name}"
    
    if [ ! -d "${ext_source}" ]; then
        echo "❌ Extension directory not found: ${ext_source}"
        return 1
    fi

    echo "📦 Installing extension: ${ext_name}..."

    # Install to ~/.gemini/extensions
    mkdir -p "${TARGET_EXT_DIR}/${ext_name}"
    cp -r "${ext_source}/"* "${TARGET_EXT_DIR}/${ext_name}/"

    # Install to ~/.gemini/antigravity-cli/plugins
    mkdir -p "${TARGET_PLUGIN_DIR}/${ext_name}"
    cp -r "${ext_source}/"* "${TARGET_PLUGIN_DIR}/${ext_name}/"

    # Setup Python Virtual Environment in ~/.gemini/extensions/<name>/venv
    local venv_path="${TARGET_EXT_DIR}/${ext_name}/venv"
    if [ ! -d "${venv_path}" ]; then
        echo "  🐍 Creating Python virtual environment at ${venv_path}..."
        python3 -m venv "${venv_path}"
    fi

    echo "  📥 Installing Python dependencies for ${ext_name}..."
    "${venv_path}/bin/pip" install --upgrade pip > /dev/null 2>&1 || true
    if [ -f "${ext_source}/requirements.txt" ]; then
        "${venv_path}/bin/pip" install -r "${ext_source}/requirements.txt"
    fi

    # Mirror venv to plugins dir if needed
    if [ ! -d "${TARGET_PLUGIN_DIR}/${ext_name}/venv" ]; then
        ln -sf "${venv_path}" "${TARGET_PLUGIN_DIR}/${ext_name}/venv"
    fi

    echo "  ✓ Extension ${ext_name} installed successfully."
}

# Function to install global skills
install_skills() {
    echo "🧠 Installing global skills to ${TARGET_SKILLS_DIR}..."
    if [ -d "${SCRIPT_DIR}/skills" ]; then
        for skill_dir in "${SCRIPT_DIR}/skills/"*; do
            if [ -d "${skill_dir}" ]; then
                local skill_name="$(basename "${skill_dir}")"
                echo "  💡 Installing skill: ${skill_name}..."
                mkdir -p "${TARGET_SKILLS_DIR}/${skill_name}"
                cp -r "${skill_dir}/"* "${TARGET_SKILLS_DIR}/${skill_name}/"
            fi
        done
    fi
    echo "  ✓ Global skills installed successfully."
}

# Install Extensions
install_extension "youtube"
install_extension "radioshow"

# Install Skills
install_skills

# Check ffmpeg
echo "🔍 Checking audio dependencies..."
if command -v ffmpeg >/dev/null 2>&1; then
    echo "  ✓ ffmpeg detected: $(ffmpeg -version | head -n1)"
else
    echo "  ⚠️ ffmpeg not detected! Please install ffmpeg for high-quality MP3 audio processing."
    echo "     Ubuntu/Debian: sudo apt update && sudo apt install -y ffmpeg"
    echo "     macOS: brew install ffmpeg"
fi

echo ""
echo "=============================================================================="
echo "🎉 Installation Complete!"
echo "You can now run commands in Antigravity CLI and Gemini CLI:"
echo "  /youtube:search \"<query>\""
echo "  /youtube:transcript \"<URL>\""
echo "  /youtube:summary \"<URL>\""
echo "  /youtube:translate \"<URL>\" <lang>"
echo "  /youtube:infographic \"<URL>\""
echo "  /youtube:podcast \"<URL>\""
echo "  /youtube:radioshow \"<URL>\" --host \"<Host Name>\""
echo "  /radioshow --topic \"<topic or text>\" --host \"<Host Name>\""
echo "=============================================================================="
