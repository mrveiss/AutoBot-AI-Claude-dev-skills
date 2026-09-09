# Social preview card

`social-preview.png` is the Open Graph image GitHub serves when a link to this
repository is pasted into Slack, X, LinkedIn or a chat. Without it, the link renders
as a grey block with the repository name.

## It has to be uploaded by hand

**A social preview is a repository setting, not a file GitHub reads from the tree**,
and there is no REST or GraphQL endpoint for it. Committing this PNG does nothing on
its own. The image lives here so that what gets uploaded is reviewable and
reproducible rather than existing only inside a settings page.

**Settings → General → Social preview → Edit → Upload an image**, and choose
`assets/social-preview.png`.

It takes effect immediately. An already-posted link may keep showing the grey block
afterwards — that is each platform's link cache, not a failed upload. Verify with a
freshly pasted link.

## Regenerating

`make_card.py` needs three fonts it does not vendor. Fetch them from Google Fonts
into `fonts/` under these exact names:

| Save as | Family |
|---|---|
| `fonts/Fraunces.ttf` | Fraunces, `opsz,wght@144,600` |
| `fonts/Schibsted.ttf` | Schibsted Grotesk, `wght@500` |
| `fonts/JetBrainsMono.ttf` | JetBrains Mono, `wght@400` |

```
python3 make_card.py --fonts ./fonts --out .
```

The script makes no network call, and fails on a missing font rather than silently
substituting one — a substituted face would change the card without changing the code.

## Design

Palette and type come from the property's landing page
([mrveiss.github.io](https://github.com/mrveiss/mrveiss.github.io)) — plum ground, wax
and cream text, the orange accent, Fraunces for display, Schibsted Grotesk for body,
JetBrains Mono for the install command — so a pasted link reads as part of the same
property.

**That page is the source of truth for these tokens and nothing enforces the match.**
If the landing page's palette changes, this file must be updated by hand. The
alternative — a shared generator in another repository — was rejected so that this
repository can regenerate its own asset without depending on another one; the cost is
that the tokens are duplicated and can drift.

**The card carries no skill count, no metrics and no badges, deliberately.** A number
baked into a setting nobody revisits becomes false the first time a skill is added,
and this is a repository whose subject is working honestly. It names domains instead,
which stays true as the set grows.
