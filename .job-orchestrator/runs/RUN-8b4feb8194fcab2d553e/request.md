# Итерация 1: Rebuild TDE Physics Core

## Контекст

Предыдущие итерации (core-renderer-01, physics-engine-02, visual-effects-03, audio-polish-04) улучшили рендеринг, физику (orbital, gravity, gas dynamics), визуальные эффекты и аудио. Однако архитектурная проверка выявила критическую проблему:

**TDE (Tidal Disruption Event)** полностью сфальсифицирован:
- Звезда — one-body объект, частицы генерируются на лету при disruption
- Tidal stream — предсозданная форма, не из физики
- Газ назначается по индексу, а не из симуляции
- Jet делается через random redirect rule, а не MHD
- Fallback rate — по таймеру t^(-5/3), не из измерений

Это нарушает **великую цель**: все явления должны возникать из общих физических уравнений.

## Цель Итерации 1

Заложить физический фундамент TDE:
1. Persistent matter particles (SPH)
2. Настоящий градиентный tidal disruption
3. Физический stream formation
4. Измеряемый fallback/circularization/accretion
5. Удаление всех фейковых механик (pre-shaped stream, index gas, random jet)

## План

### J001 — Proposal
- openspec explore текущего состояния TDE
- Проверить, актуален ли существующий proposal rebuild-tde-physics-core
- Если нужны изменения — обновить proposal
- Передать Implementation

### J002 — Implementation (Task Groups 1-3)
- Physics State Foundation: единая политика юнитов, persistent particle state, polytropic initializer
- Neighbor Search & SPH: spatial hash, density, pressure, forces, internal energy
- Unified Gravity: symplectic integration, BH + self-gravity, pseudo-Newtonian potential

### J003 — Implementation (Task Groups 4-5)
- TDE Initial Conditions & Disruption: persistent star, real tidal gradient, disruption detection
- Fallback, Circularization, Accretion: bound/unbound classification, particle capture, remove fake timers

### J004 — Implementation (Task Groups 6-7)
- Physics State & Rendering Contract: update getState(), remove TDE-specific hacks
- Verification & Performance: integration tests, benchmarks, docs

### J005 — Architect (Cross-cutting Review)
- Проверить все изменения против великой цели
- Убедиться что ни один фейковый механизм не остался
- Проверить совместимость с существующими фичами (visual-effects-03, audio-polish-04)
- Спланировать Итерацию 2
