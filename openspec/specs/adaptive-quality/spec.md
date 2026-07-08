# adaptive-quality

## Requirements

### Requirement: FPS monitoring
The system SHALL track frame rate using a rolling average of the last 60 frames. The average FPS SHALL be available to other systems (UI display, quality adjustment).

#### Scenario: Rolling FPS average
- **WHEN** the render loop is running
- **THEN** the system SHALL compute the average FPS over the last 60 frames and expose it as a readable property

### Requirement: Quality levels
The system SHALL define 5 quality levels: Minimum, Low, Medium, High, and Auto. Each level configures lensing resolution, ray-march steps, particle budget, and post-processing effects. Star count is NOT controlled by quality level — it is a user-only setting in celestial-background.

#### Scenario: Minimum quality settings
- **WHEN** quality level is set to "Minimum"
- **THEN** lensing SHALL render at half resolution, ray-march SHALL use 10 steps, particle budget SHALL be 6,000, and all post-processing SHALL be disabled

#### Scenario: Low quality settings
- **WHEN** quality level is set to "Low"
- **THEN** lensing SHALL render at half resolution, ray-march SHALL use 15 steps, particle budget SHALL be 12,000, and FXAA SHALL be disabled

#### Scenario: Medium quality settings
- **WHEN** quality level is set to "Medium"
- **THEN** lensing SHALL render at half resolution, ray-march SHALL use 20 steps, particle budget SHALL be 20,000, and FXAA SHALL be enabled

#### Scenario: High quality settings
- **WHEN** quality level is set to "High"
- **THEN** lensing SHALL render at full resolution, ray-march SHALL use 30 steps, particle budget SHALL be 35,000, and full post-processing SHALL be active

### Requirement: Auto quality adjustment
When quality is set to "Auto", the system SHALL automatically adjust quality levels based on measured FPS. If FPS drops below 28 for 120+ frames, quality SHALL downgrade. If FPS exceeds 55 for 120+ frames, quality SHALL upgrade.

#### Scenario: Auto-downgrade on low FPS
- **WHEN** quality is "Auto" and average FPS is below 28 for 120 consecutive frames
- **THEN** the system SHALL reduce quality by one level (High→Medium, Medium→Low, Low→Minimum)

#### Scenario: Auto-upgrade on high FPS
- **WHEN** quality is "Auto" and average FPS is above 55 for 120 consecutive frames
- **THEN** the system SHALL increase quality by one level (Minimum→Low, Low→Medium, Medium→High)

#### Scenario: No rapid switching
- **WHEN** a quality adjustment has just been made
- **THEN** the system SHALL wait at least 120 frames before making another adjustment

### Requirement: Minimum quality frame skip
When quality is set to "Minimum" and FPS still falls below 20, the system SHALL skip rendering every other frame to maintain acceptable visual fluidity.

#### Scenario: Frame skip activates at very low FPS
- **WHEN** quality is "Minimum" and average FPS is below 20 for 60 consecutive frames
- **THEN** the system SHALL skip rendering every other frame (render at half frame rate)

#### Scenario: Frame skip deactivates when FPS recovers
- **WHEN** frame skip is active and average FPS rises above 25 for 60 consecutive frames
- **THEN** the system SHALL resume rendering every frame

#### Scenario: Frame skip does not affect physics
- **WHEN** frame skip is active
- **THEN** the physics engine SHALL continue to update at full rate; only rendering is skipped

### Requirement: Quality applies to lensing resolution
The quality level SHALL control whether the lensing shader renders at full or half canvas resolution.

#### Scenario: Half-resolution lensing
- **WHEN** quality is "Minimum", "Low", or "Medium"
- **THEN** the lensing pass SHALL render to a framebuffer at 50% of canvas dimensions

#### Scenario: Full-resolution lensing
- **WHEN** quality is "High"
- **THEN** the lensing pass SHALL render to a framebuffer at 100% of canvas dimensions

### Requirement: Quality applies to ray-march steps
The quality level SHALL control the number of ray-march steps in the lensing shader.

#### Scenario: Minimum steps at minimum quality
- **WHEN** quality is "Minimum"
- **THEN** the lensing shader SHALL perform 10 ray-march steps per pixel

#### Scenario: Reduced steps at low quality
- **WHEN** quality is "Low"
- **THEN** the lensing shader SHALL perform 15 ray-march steps per pixel

#### Scenario: Full steps at high quality
- **WHEN** quality is "High"
- **THEN** the lensing shader SHALL perform 30 ray-march steps per pixel

### Requirement: Quality applies to particle budget
The quality level SHALL control the maximum number of particles rendered per frame. Exceeding the budget SHALL cull particles.

#### Scenario: Minimum particle budget
- **WHEN** quality is "Minimum"
- **THEN** the particle renderer SHALL render at most 6,000 particles

#### Scenario: Low particle budget
- **WHEN** quality is "Low"
- **THEN** the particle renderer SHALL render at most 12,000 particles

### Requirement: Quality selector UI
The system SHALL provide a UI dropdown or button group to select between Minimum, Low, Medium, High, and Auto quality levels. The current quality level SHALL be visually indicated.

#### Scenario: Change quality via UI
- **WHEN** the user clicks a quality level button
- **THEN** the quality level SHALL change immediately and the renderer SHALL apply the new settings on the next frame

#### Scenario: Auto quality shows current level
- **WHEN** quality is set to "Auto"
- **THEN** the UI SHALL display the actual quality level being used (e.g., "Auto (Medium)")
