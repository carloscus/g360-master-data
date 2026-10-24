function LoadingOverlay({ message = 'Cargando...' }) {
  return (
    <div className="g360-loading-overlay">
      <div className="g360-loading-spinner" />
      <p>{message}</p>
    </div>
  );
}

export default LoadingOverlay;
