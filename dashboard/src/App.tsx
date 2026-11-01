import {
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import Layout from "./components/Layout";
import Marche from "./pages/Marche";
import Portefeuille from "./pages/Portefeuille";
import Agent from "./pages/Agent";
import Traces from "./pages/Traces";

const rootRoute = createRootRoute({ component: Layout });

const routes = [
  createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: Marche,
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: "/marche",
    component: Marche,
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: "/portefeuille",
    component: Portefeuille,
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: "/agent",
    component: Agent,
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: "/traces",
    component: Traces,
  }),
];

const router = createRouter({
  routeTree: rootRoute.addChildren(routes),
  defaultPreload: "intent",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

export default function App() {
  return <RouterProvider router={router} />;
}
