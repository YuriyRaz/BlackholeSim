## ADDED Requirements

### Requirement: Single-finger orbit
A single finger drag on touch devices SHALL orbit the camera around the focus point, equivalent to left-mouse-drag on desktop.

#### Scenario: One finger orbits camera
- **WHEN** the user drags with one finger on a touch device
- **THEN** the camera SHALL orbit around the focus point

### Requirement: Two-finger pan
A two-finger drag on touch devices SHALL pan the camera focus point, equivalent to right-mouse-drag on desktop.

#### Scenario: Two fingers pan camera
- **WHEN** the user drags with two fingers on a touch device
- **THEN** the camera focus point SHALL move in the screen plane

### Requirement: Pinch zoom
A pinch gesture on touch devices SHALL zoom the camera in/out, equivalent to scroll wheel on desktop.

#### Scenario: Pinch to zoom
- **WHEN** the user performs a pinch gesture
- **THEN** the camera SHALL zoom in (pinch out) or out (pinch in)

### Requirement: Double-tap focus
A double-tap on a touch device SHALL focus the camera on the nearest object at the tap location, equivalent to click-to-focus on desktop.

#### Scenario: Double-tap focuses object
- **WHEN** the user double-taps near a celestial object
- **THEN** the camera SHALL smoothly transition to focus on that object

### Requirement: Touch gesture conflict prevention
The canvas element SHALL use `touch-action: none` CSS to prevent browser default touch gestures (scroll, zoom) from interfering with camera controls.

#### Scenario: No browser gesture interference
- **WHEN** the user performs touch gestures on the canvas
- **THEN** the browser SHALL NOT scroll the page or zoom the viewport

### Requirement: Touch visual feedback
Touch interactions SHALL provide subtle visual feedback (ripple effect or highlight) at the touch point to confirm input registration.

#### Scenario: Touch feedback visible
- **WHEN** the user touches the canvas
- **THEN** a subtle visual indicator SHALL appear at the touch point for 200ms
