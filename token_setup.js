() => {
  // Set token note
  const noteInput = document.querySelector('#token_description');
  if (!noteInput) return 'Note input not found';
  noteInput.value = 'lan-scanner-push-token';
  noteInput.dispatchEvent(new Event('input', { bubbles: true }));

  // Check repo scope (full control of private repositories)
  const repoCheckbox = document.querySelector('input[value="repo"]');
  if (repoCheckbox) {
    repoCheckbox.checked = true;
    repoCheckbox.dispatchEvent(new Event('change', { bubbles: true }));
  }

  return 'Fields set: note=' + noteInput.value + ', repo-checked=' + (repoCheckbox ? repoCheckbox.checked : 'not found');
}
