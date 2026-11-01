/**
 * Vrai si l'erreur vient d'un `AbortController.abort()` (annulation voulue, pas une panne).
 * On regarde le nom plutôt que `instanceof Error` : selon l'environnement (navigateur, jsdom),
 * l'erreur d'annulation est un `DOMException` qui n'hérite pas toujours de `Error`.
 */
export function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "AbortError"
  );
}
