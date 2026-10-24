import { useState } from 'react';
import Header from './components/Header';
import LoadingOverlay from './components/LoadingOverlay';
import FooterSignature from './components/FooterSignature';

function App() {
  const [loading, setLoading] = useState(false);

  return (
    <div className="app">
      <Header />
      <main className="container">
        <h1>Bienvenido a G360</h1>
        <p className="muted">Proyecto creado con React + Vite</p>
      </main>
      <FooterSignature />
      {loading && <LoadingOverlay message="Cargando..." />}
    </div>
  );
}

export default App;
