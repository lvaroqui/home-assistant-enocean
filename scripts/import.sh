
#!/usr/bin/env bash

# This script imports a specific integration from a Home Assistant fork into this repository.
# Usage: import.sh <remote_url> <git_ref> <integration>

set -e

if [ "$#" -ne 4 ]; then
	echo "Usage: $0 <remote_name> <remote_url> <git_ref> <integration>"
	exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."

REMOTE_NAME="$1"
REMOTE_URL="$2"
GIT_REF="$3"
INTEGRATION="$4"

HA_DIR=".home-assistant"

# Ensure .home-assistant exists and is the main repo
if [ ! -d "$HA_DIR/.git" ]; then
	rm -rf "$HA_DIR"
    mkdir "$HA_DIR"
    git -C "$HA_DIR" init
fi

cd "$HA_DIR"

# Add or update the remote
if git remote | grep -q "^$REMOTE_NAME$"; then
	git remote set-url "$REMOTE_NAME" "$REMOTE_URL"
else
	git remote add "$REMOTE_NAME" "$REMOTE_URL"
fi

git fetch "$REMOTE_NAME"
git checkout FETCH_HEAD
git checkout "$GIT_REF"
python -m script.translations develop --integration "$INTEGRATION"

cd "$ROOT_DIR"

# Copy the integration
SRC_PATH="$HA_DIR/homeassistant/components/$INTEGRATION"
DEST_PATH="custom_components/$INTEGRATION"
MANIFEST_FILE="$DEST_PATH/manifest.json"
current_version="1.0.0"

if [ -f "$MANIFEST_FILE" ] && command -v jq >/dev/null 2>&1; then
	manifest_version=$(jq -r '.version // empty' "$MANIFEST_FILE")
	if [ -n "$manifest_version" ]; then
		current_version="$manifest_version"
	fi
fi

major=$(printf '%s' "$current_version" | cut -d. -f1)
if [ -z "$major" ]; then
	major=1
fi
new_major=$((major + 1))
new_version="$new_major.0.0"

if [ ! -d "$SRC_PATH" ]; then
	echo "Integration '$INTEGRATION' not found in source repository."
	exit 2
fi

echo "Copying integration '$INTEGRATION' to custom_components..."
rm -rf "$DEST_PATH"
cp -r "$SRC_PATH" "$DEST_PATH"

echo "Import complete."

if [ -f "$MANIFEST_FILE" ]; then
	if command -v jq >/dev/null 2>&1; then
		tmpfile=$(mktemp)
		jq --arg version "$new_version" '.version = $version' "$MANIFEST_FILE" > "$tmpfile" && mv "$tmpfile" "$MANIFEST_FILE"
		echo "Set version to $new_version in $MANIFEST_FILE using jq."
	else
		echo "jq not found, skipping version update in $MANIFEST_FILE."
	fi
else
	echo "Manifest not found, default version is 1.0.0."
fi
