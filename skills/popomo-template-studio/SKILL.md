---
name: popomo-template-studio
description: Create or extend POPOMO editable phone-case templates, photo and sticker content, and the reusable simulated AI beautification component. Use for this project's DIY content production and component maintenance.
---

# POPOMO template studio

Use the existing POPOMO project and its confirmed creator-content specification. Preserve Simplified Chinese / US English, USD, fixed case shells with UV-printed artwork, ivory surfaces, pink #E44592 and teal #30B7B9.

## Content structure

- Publish three types: photo, sticker, case. Photos and stickers may be independent content; a full case design is an editable composition.
- Every visible template word belongs in a text layer; graphic elements belong in individual sticker/image layers. An imported photo remains one image layer, not an automatically decomposable photograph.
- Preserve the editor's x/y percentage positions, size, rotation, stable layer IDs and undo history. Keep under the supported layer limit.
- Preserve content ID, creator ID and source version on every referenced layer. A full design's creator is distinct from each embedded asset's creator.
- Use supplied assets or built-in image_gen for new raster artwork; use native SVG assets when extending the project's existing vector style. Do not claim generated imagery is real case material or tested UV output.

## Beautification component

- The current user-approved mode is a local simulation. Label the component “AI 美化 · 模拟” / “AI enhancement · Demo”. It must not claim real inference, inpainting or background removal.
- Generate a cloned preview with explicit options. Keep original text, assets, creator attribution and editable layers. Do not flatten the composition.
- Require an Apply action before changing the current design; Cancel and failures preserve it. Applying is one undo operation. Reject a preview if the source design changed after generation.
- Real AI requires a separate server integration and service configuration; installing this skill does not make a browser call the assistant or image_gen tool.

## Delivery checks

Check saved/reloaded layers, mobile drag and numeric controls, both languages, newly published content visibility and provenance, apply/cancel/undo, and both simulated delivery paths. Keep creator workspace behind assigned demo accounts; frontend-only permissions are simulation, not production authorization.

Keep changes in the project with tests, asset provenance and user-facing preview. Do not change prices, commission rules, shipping restrictions or real service integrations merely while adding content.
