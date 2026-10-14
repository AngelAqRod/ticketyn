export function confirmDeactivation(): boolean {
  return window.confirm('¿Desactivar este registro? Dejará de aparecer en selectores operativos nuevos. Los tickets históricos seguirán conservando la referencia. El registro no se eliminará.')
}
