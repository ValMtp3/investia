export default function Agent() {
  return (
    <section aria-labelledby="agent-title">
      <h1 id="agent-title" className="text-2xl font-bold mb-4">
        Conseils de l'agent
      </h1>
      <p className="text-slate-400">
        Le chat agent (AG-UI, streaming SSE) arrive à l'étape 4.4. En attendant, l'agent tourne en
        ligne de commande : <code>uv run python -m investia.cli "prix de AAPL ?"</code>
      </p>
    </section>
  );
}
