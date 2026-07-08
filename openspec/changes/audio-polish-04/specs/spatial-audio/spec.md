## ADDED Requirements

### Requirement: HRTF 3D panning
Each black hole SHALL have a PannerNode with HRTF (Head-Related Transfer Function) panning model. Sound from each black hole SHALL appear to come from its 3D position.

#### Scenario: Sound from left black hole
- **WHEN** a black hole is to the left of the camera
- **THEN** its sound SHALL be louder in the left ear/speaker

#### Scenario: Sound follows black hole movement
- **WHEN** a black hole moves during simulation
- **THEN** its panner position SHALL update each frame to match

### Requirement: Distance attenuation
Audio from each source SHALL attenuate with distance using inverse square law: gain = 1 / (1 + distance²).

#### Scenario: Louder when close
- **WHEN** the camera is close to a black hole
- **THEN** its sound SHALL be at maximum volume

#### Scenario: Quieter when far
- **WHEN** the camera is far from a black hole
- **THEN** its sound SHALL decrease significantly

### Requirement: Doppler pitch shift
The system SHALL apply Doppler pitch shift to audio sources based on relative velocity between the camera and the source. Approaching sources SHALL have slightly higher pitch; receding sources SHALL have lower pitch.

#### Scenario: Approaching source pitch shift
- **WHEN** a black hole is moving toward the camera
- **THEN** its sound SHALL have a slightly higher pitch (up to 5%)

#### Scenario: Receding source pitch shift
- **WHEN** a black hole is moving away from the camera
- **THEN** its sound SHALL have a slightly lower pitch (up to 5%)

### Requirement: Spatial audio updates each frame
The AudioEngine SHALL update all panner positions, distances, and Doppler shifts each frame to maintain accurate spatialization.

#### Scenario: Spatial audio stays synchronized
- **WHEN** the camera moves rapidly
- **THEN** the spatial audio SHALL update within one frame to match the new perspective
