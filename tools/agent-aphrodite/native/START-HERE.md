# Aphrodite: design with the whole in mind

You are the designer. Bring your full frontend ability, visual imagination, subject knowledge, and judgment. Aphrodite gives you a language for making the parts answer one another, and a small runtime for keeping those relationships alive in code. Your existing design skills and the project's native frontend remain the working medium.

The aim is a page that feels inevitable for its subject: a particular encounter, with something worth looking at and a clear reason to act. A capable AI already knows a great deal about this. Use that knowledge.

## Begin with the encounter

Read the user's brief and the working project. If present, `BRIEF.txt` preserves the supplied brief verbatim. `SOURCE-CONTEXT.json` preserves an older structured brief and its embedded assets; treat its content, intended roles, and identity as source material. Its old grammar and scoring weights do not govern this workflow.

Name the encounter in one sentence: who is here, what matters to them, and what this place should make possible. Then imagine its emotional movement. A research instrument might move from overview to close examination. A shop might move from desire to confident choice. A reading experience might alternate intimacy and discovery. These are possibilities, not page templates.

Let the subject suggest the material world: type with a particular voice, useful density, image treatment, rhythm, color, and behavior. Make a concrete design decision early. Keep this reasoning in your working notes; the product speaks to its users through real content and usable controls.

## Compose freely, then make the relationships explicit

Use the normal frontend-design workflow and the existing stack. You can write any appropriate components, CSS, SVG, canvas, motion, imagery, tables, forms, and responsive behavior. The content can determine its own topology. An instrument row, an illustrated scene, a product comparison, and a reading column need not have the same anatomy.

For an existing page, inspect and preserve the strongest parts before changing it. For a new page, make a strong native composition first. Keep that version as a visible comparison. This is a practical reference, not a blinded experiment establishing improvement.

Find the few relationships on which this particular whole depends. Examples:

- A headline gathers the supporting copy closer as its presence increases.
- Quiet labels repeat a common alignment while important values vary in width.
- A pale expanse gives one small, saturated object enough visual force.
- The image crop and a text column aim toward the same focal point.
- Dense working rows share a baseline; breathing space separates changes of task.
- A motif returns in another material, so the page remembers itself without repeating a component.

Use `RELATIONSHIPS.md` as a vocabulary of possible moves. Choose the ones that serve the encounter. Elaborate a different relationship when the subject calls for it. The vocabulary is open.

Record a relationship as: **parts → intended connection → coordinated change → expected visible consequence → context where it would stop helping**. Include geometry, material, and meaning where they interact. A number is an authored coordinate for this composition, unless an actual source supports a stronger claim.

## Give the relationships a body

Implement them in the frontend's own tokens, layout rules, components, and responsive logic. CSS already expresses many relationships well. Use it directly when that is clearer.

For coupled numerical changes, edit `relations.json`. Its inputs and derived nodes are named by you. It has no fixed five controls, component catalog, preferred palette, or beauty weights. `EXAMPLE.json` demonstrates the syntax on invented values; it is not a starting aesthetic to copy.

Run from this packet:

```bash
node runtime/relation-cli.js --relations relations.json --out revision --set yourInput=1.2
```

Or, using the installed tool:

```bash
agent-do aphrodite describe --relations relations.json
agent-do aphrodite revise --relations relations.json --out revision --set yourInput=1.2
```

Include the emitted `revision/relations.css` in your frontend. It defines only the CSS custom properties you bound. Your selectors decide where those variables apply. The accompanying graph becomes the starting point for the next revision.

For live interaction, import `applyRelations` from `runtime/relations.js` and call `applyRelations(element, graph, overrides)`. It evaluates the complete graph before setting the named custom properties on that element. In React or another framework, use the resolved variables through the framework's normal style mechanism if that fits the project better. No framework adapter is required.

The runtime carries numerical dependencies. You still author nonnumerical relationships: which illustration belongs here, which typeface speaks in the right voice, how navigation unfolds, and where a layout changes shape. These remain explicit design choices, not hidden model scores.

## Look at what you made

Render the actual frontend with its real content. Use the project's browser workflow, or `agent-do browse`, to inspect it at its relevant sizes and states. Read the page as a whole, then follow the task, then inspect the detail. Measurements explain a visual consequence; the screenshot and working page expose consequences your arithmetic did not represent.

Make a coordinated alternative to the relationship most likely to improve the whole. Compare it with the saved version. Use your visual judgment to choose, just as you do in ordinary frontend design, and state the concrete reason. Preserve what was working. If the intervention weakens the composition, retain the better version and reconsider the relationship.

Do not route native designs through `compose`, an affinity ranking, or the nine legacy families. Those belong to the earlier experimental generator. Its numerical ordering has not earned authority over this work. Human verdicts, when supplied, stay attributed and distinct from your own design assessment.

## Leave continuity, not a manifesto

Deliver the working frontend. Leave a compact design note naming its intention, strongest relationships, owned tokens or components, and where you inspected it. Include the saved comparison when it makes a consequential choice easier to assess.

The next session should be able to make a change without erasing the composition's character. That is what the relationship graph is for.
