export function operationalChoice(person: { active: boolean; operational_selectable?: boolean; id: number }, retained: readonly (string | number)[] = []) {
  return person.active && person.operational_selectable !== false || retained.some(id => String(id) === String(person.id))
}
