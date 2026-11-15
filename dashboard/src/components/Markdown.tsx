import { Streamdown } from "streamdown";

/**
 * 23f : rendu markdown des réponses de l'agent (streamdown 2.7.1, Vercel —
 * listes, tableaux, blocs de code). La DA de la page est inchangée : on garde
 * le conteneur (couleur/overflow) autour du contenu markdown.
 */
export default function Markdown({ children }: { children: string }) {
  return <Streamdown>{children}</Streamdown>;
}
