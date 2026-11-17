export const formatDate = value => new Date(`${value}T12:00:00`).toLocaleDateString('fr-FR',{weekday:'short',day:'numeric',month:'short'});
export const duration = seconds => {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor(total % 3600 / 60);
  const rest = total % 60;
  if (hours) return `${hours} h ${minutes} min`;
  return minutes ? `${minutes} min${rest ? ` ${rest} s` : ''}` : `${rest} s`;
};
export const extracts = count => `${count} extrait${count === 1 ? '' : 's'} avec aboiements`;
export const files = count => `${count} fichier${count === 1 ? '' : 's'} audio`;
export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}


export const timestamp = seconds => {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};
