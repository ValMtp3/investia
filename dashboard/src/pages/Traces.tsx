import Module from "../components/Module";

export default function Traces() {
  return (
    <section aria-labelledby="traces-title">
      <h1 id="traces-title" className="mb-3 text-lg font-bold">
        Traces & évaluations
      </h1>
      <Module title="Exécutions et évaluations">
        <p className="max-w-prose text-muted">
          L'affichage des exécutions (runs) et des scores d'evals arrive avec les pages complètes de
          l'étape 4. Les données sont déjà en base : tables <code>runs</code>, <code>run_steps</code>,{" "}
          <code>eval_runs</code>, <code>eval_results</code>.
        </p>
      </Module>
    </section>
  );
}
