## ADDED Requirements

### Requirement: FPS monitoring
The system SHALL track frame rate using a rolling average of the last 60 frames. The average FPS SHALL be available to other systems (UI display, quality adjustment).

#### Scenario: Rolling FPS average
- **WHEN** the render loop is running
- **THEN** the system SHALL compute the average FPS over the last 60 frames and expose it as a readable property

### Requirement: Quality levels
The system SHALL define 4 quality levels: Low, Medium, High, and Auto. Each level configures lensing resolution, ray-march steps, star count, and post-processing effects.

#### Scenario: Low quality settings
- **WHEN** quality level is set to "Low"
- **THEN** lensing SHALL render at half resolution, ray-march SHALL use 15 steps, stars SHALL be 1000, and FXAA SHALL be disabled

#### Scenario: Medium quality settings
- **WHEN** quality level is set to "Medium"
- **THEN** lensing SHALL render at half resolution, ray-march SHALL use 20 steps, stars SHALL be 2000, and FXAA SHALL be enabled

#### Scenario: High quality settings
- **WHEN** quality level is set to "High"
- **THEN** lensing SHALL render at full resolution, ray-march SHALL use 30 steps, stars SHALL be 3000, and full post-processing SHALL be active

### Requirement: Auto quality adjustment
When quality is set to "Auto", the system SHALL automatically adjust quality levels based on measured FPS. If FPS drops below 28 for 120+ frames, quality SHALL downgrade. If FPS exceeds 55 for 120+ frames, quality SHALL upgrade.

#### Scenario: Auto-downgrade on low FPS
- **WHEN** quality is "Auto" and average FPS is below 28 for 120 consecutive frames
- **THEN** the system SHALL reduce quality by one level (High→Medium, Medium→Low)

#### Scenario: Auto-upgrade on high FPS
- **WHEN** quality is "Auto" and average FPS is above 55 for 120 consecutive frames
- **THEN** the system SHALL increase quality by one level (Low→Medium, Medium→High)

#### Scenario: No rapid switching
- **WHEN** a quality adjustment has just been made
- **THEN** the system SHALL wait at least 120 frames before making another adjustment

### Requirement: Quality applies to lensing resolution
The quality level SHALL control whether the lensing shader renders at full or half canvas resolution.

#### Scenario: Half-resolution lensing
- **WHEN** quality is "Low" or "Medium"
- **THEN** the lensing pass SHALL render to a framebuffer at 50% of canvas dimensions

#### Scenario: Full-resolution lensing
- **WHEN** quality is "High"
- **THEN** the lensing pass SHALL render to a framebuffer at 100% of canvas dimensions

### Requirement: Quality applies to ray-march steps
The quality level SHALL control the number of ray-march steps in the lensing shader.

#### Scenario: Reduced steps at low quality
- **WHEN** quality is "Low"
- **THEN** the lensing shader SHALL perform 15 ray-march steps per pixel

#### Scenario: Full steps at high quality
- **WHEN** quality is "High"
- **THEN** the lensing shader SHALL perform 30 ray-march steps per pixel

### Requirement: Quality selector UI
The system SHALL provide a UI dropdown or button group to select between Low, Medium, High, and Auto quality levels. The current quality level SHALL be visually indicated.

#### Scenario: Change quality via UI
- **WHEN** the user clicks a quality level button
- **THEN** the quality level SHALL change immediately and the renderer SHALL apply the new settings on the next frame

#### Scenario: Auto quality shows current level
- **WHEN** quality is set to "Auto"
- **THEN** the UI SHALL display the actual quality level being used (e.g., "Auto (Medium)")
