---
name: f01-native-date
tags: [code, ponytail-owned]
max_turns: 3
allowed_tools: []
---

Our signup page is plain HTML and vanilla JavaScript with no build step and no package.json. Add a birthdate field to the form below. Users must pick a date, and a birthdate in the future is invalid. Reply with the complete updated form in one fenced code block.

```html
<form id="signup" action="/signup" method="post">
  <label for="email">Email</label>
  <input id="email" name="email" type="email" required>
  <button type="submit">Sign up</button>
</form>
```
