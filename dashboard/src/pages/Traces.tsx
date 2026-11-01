export default function Traces() {
  return (
    <section aria-labelledby="traces-title">
      <h1 id="traces-title" className="text-2xl font-bold mb-4">
        Traces & évaluations
      </h1>
      <p className="text-slate-400">
        L'affichage des exécutions (runs) et des scores d'evals arrive avec les pages complètes de
        l'étape 4. Les données sont déjà en base : tables <code>runs</code>, <code>run_steps</code>,{" "}
        <code>eval_runs</code>, <code>eval_results</code>.
      </p>
    </section>
  );
}
