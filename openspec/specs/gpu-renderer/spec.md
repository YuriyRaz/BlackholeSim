# gpu-renderer

## Requirements

### Requirement: GPU backend abstraction
The system SHALL provide a unified rendering interface that abstracts over WebGPU and WebGL 2.0 backends. The renderer SHALL automatically detect available GPU APIs and select the best available backend.

#### Scenario: WebGPU available
- **WHEN** the browser supports WebGPU (`navigator.gpu` exists and adapter is requestable)
- **THEN** the renderer SHALL initialize with WebGPU backend and use WGSL shaders

#### Scenario: WebGPU unavailable, WebGL 2.0 available
- **WHEN** the browser does not support WebGPU but supports WebGL 2.0
- **THEN** the renderer SHALL initialize with WebGL 2.0 backend and use GLSL shaders

#### Scenario: Neither GPU API available
- **WHEN** the browser supports neither WebGPU nor WebGL 2.0
- **THEN** the renderer SHALL display an error message indicating browser incompatibility and SHALL NOT attempt to render

### Requirement: Shader compilation
The system SHALL compile vertex and fragment shaders from source (WGSL or GLSL depending on backend) and report compilation errors with descriptive messages.

#### Scenario: Valid shader compiles successfully
- **WHEN** a valid shader source is provided to `createShader()`
- **THEN** the system SHALL return a compiled shader handle without errors

#### Scenario: Invalid shader produces error
- **WHEN** a shader with syntax errors is provided to `createShader()`
- **THEN** the system SHALL throw an error containing the shader stage (vertex/fragment), line number, and error description

### Requirement: Render pass management
The system SHALL support multiple sequential render passes within a single frame, where each pass can target a different framebuffer or the screen.

#### Scenario: Multiple passes compose final frame
- **WHEN** the renderer executes a frame with passes [background, lensing, disk, postprocess]
- **THEN** each pass SHALL execute in order, with the output of one pass available as input to subsequent passes

#### Scenario: Offscreen framebuffer rendering
- **WHEN** a render pass targets an offscreen framebuffer
- **THEN** the rendered result SHALL be available as a texture input to subsequent passes

### Requirement: Framebuffer management
The system SHALL create and manage offscreen framebuffers for multi-pass rendering, including depth buffers and color attachments.

#### Scenario: Create framebuffer with dimensions
- **WHEN** `createFramebuffer(width, height)` is called
- **THEN** the system SHALL allocate a GPU framebuffer with the specified dimensions and return a handle

#### Scenario: Resize framebuffer
- **WHEN** `resizeFramebuffer(handle, newWidth, newHeight)` is called
- **THEN** the system SHALL reallocate the framebuffer with new dimensions and preserve no content from the previous allocation

### Requirement: Canvas management
The system SHALL manage a WebGL/WebGPU canvas element that fills its container, handles device pixel ratio, and responds to window resize events.

#### Scenario: Canvas fills container
- **WHEN** the renderer initializes with a container element
- **THEN** the canvas SHALL fill 100% of the container's width and height

#### Scenario: Window resize updates canvas
- **WHEN** the browser window is resized
- **THEN** the canvas SHALL update its dimensions to match the container within 100ms and the renderer SHALL update its viewport accordingly

### Requirement: Post-processing pipeline
The system SHALL apply post-processing effects to the final rendered frame using a fullscreen quad pass. The pipeline SHALL support bloom, tone mapping, FXAA, and vignette as composable stages.

#### Scenario: Bloom applied to bright areas
- **WHEN** the post-processing pipeline is active
- **THEN** pixels brighter than 1.0 SHALL have their brightness spread to neighboring pixels with configurable radius and intensity

#### Scenario: ACES tone mapping
- **WHEN** the post-processing pipeline is active
- **THEN** HDR values SHALL be mapped to LDR using the ACES filmic tone mapping curve

#### Scenario: FXAA anti-aliasing
- **WHEN** the post-processing pipeline is active
- **THEN** jaggies on high-contrast edges SHALL be smoothed using FXAA algorithm

#### Scenario: Post-processing disabled
- **WHEN** the user disables post-processing via the display toggles
- **THEN** the scene SHALL render directly to screen without any post-processing passes

### Requirement: Frame timing
The system SHALL use `requestAnimationFrame` for the render loop and provide accurate delta time in seconds to all update callbacks.

#### Scenario: Consistent frame timing
- **WHEN** the render loop is running
- **THEN** `requestAnimationFrame` SHALL be called on each frame and delta time SHALL be calculated from `performance.now()` timestamps

#### Scenario: Pause when tab hidden
- **WHEN** the browser tab becomes hidden (visibility change event)
- **THEN** the render loop SHALL pause and delta time SHALL reset to 0 when the tab becomes visible again

### Requirement: Screen-to-world ray casting
The system SHALL provide a function to convert screen-space coordinates to a world-space ray (origin + direction). This ray SHALL be computed by unprojecting the screen coordinate through the inverse view-projection matrix.

#### Scenario: Screen coordinate produces world ray
- **WHEN** `screenToWorldRay(screenX, screenY)` is called with valid screen coordinates
- **THEN** the system SHALL return a ray with world-space origin (camera position) and a normalized direction vector pointing from the camera through the specified pixel

#### Scenario: Ray origin at camera position
- **WHEN** a screen-to-world ray is computed
- **THEN** the ray origin SHALL be the camera's world-space position

#### Scenario: Ray direction through pixel center
- **WHEN** a screen-to-world ray is computed for pixel (x, y)
- **THEN** the ray direction SHALL point from the camera through the center of that pixel in world space

### Requirement: Object picking via ray intersection
The system SHALL provide a function to test a world-space ray against all visible celestial bodies and return the closest intersected body. The system SHALL use ray-sphere intersection testing.

#### Scenario: Ray hits a star
- **WHEN** `pickObject(ray, bodies)` is called and the ray intersects a star body
- **THEN** the system SHALL return the star body and its intersection distance

#### Scenario: Ray hits a black hole
- **WHEN** the ray intersects a black hole's event horizon sphere
- **THEN** the system SHALL return the black hole body and its intersection distance

#### Scenario: Ray hits a neutron star
- **WHEN** the ray intersects a neutron star body
- **THEN** the system SHALL return the neutron star body and its intersection distance

#### Scenario: Ray hits nothing
- **WHEN** the ray does not intersect any body
- **THEN** the system SHALL return null

#### Scenario: Ray hits multiple bodies
- **WHEN** the ray intersects multiple bodies
- **THEN** the system SHALL return the closest body (smallest intersection distance)

### Requirement: Ray-sphere intersection
The picking system SHALL use geometric ray-sphere intersection testing. The sphere for each body type SHALL be: star → `body.radius`, black hole → event horizon radius (Rs = 2GM/c²), neutron star → `body.radius`.

#### Scenario: Intersection distance calculation
- **WHEN** a ray tests against a body's bounding sphere
- **THEN** the system SHALL compute the parametric intersection distance t along the ray, and return the closest positive t value
