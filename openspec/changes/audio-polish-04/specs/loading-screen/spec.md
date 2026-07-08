## ADDED Requirements

### Requirement: Loading screen displays during asset loading
The system SHALL show a loading screen overlay while assets (textures, shaders) are being loaded and compiled. The loading screen SHALL display a progress bar and descriptive text.

#### Scenario: Loading screen appears on startup
- **WHEN** the application begins loading
- **THEN** a loading overlay SHALL appear covering the entire viewport

#### Scenario: Progress bar shows loading progress
- **WHEN** assets are loading
- **THEN** the progress bar SHALL advance from 0% to 100% as assets load

### Requirement: Loading screen phases
The loading screen SHALL show two phases: "Loading textures..." (0-50%) and "Compiling shaders..." (50-100%).

#### Scenario: Texture loading phase
- **WHEN** the nebula texture is loading
- **THEN** the progress bar SHALL be at 0-50% and text SHALL show "Loading textures..."

#### Scenario: Shader compilation phase
- **WHEN** shaders are compiling
- **THEN** the progress bar SHALL be at 50-100% and text SHALL show "Compiling shaders..."

### Requirement: Loading screen fades out
When loading completes, the loading screen SHALL fade out over 0.5 seconds and then be removed from the DOM.

#### Scenario: Loading completes
- **WHEN** all assets are loaded and shaders compiled
- **THEN** the loading screen SHALL fade to transparent over 0.5 seconds

### Requirement: Loading screen shows preview
The loading screen SHALL display a static preview image or the application title/logo while loading.

#### Scenario: Preview visible during load
- **WHEN** the loading screen is displayed
- **THEN** a preview image or title SHALL be visible behind the progress bar

### Requirement: Loading screen handles errors
If asset loading fails, the loading screen SHALL display an error message with details and a retry button.

#### Scenario: Asset loading fails
- **WHEN** a texture fails to load or a shader fails to compile
- **THEN** the loading screen SHALL show an error message and a "Retry" button
