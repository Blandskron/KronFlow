interface GoogleIdentity {
  initialize(options: {
    client_id: string;
    nonce: string;
    auto_select: boolean;
    callback: (response: { credential: string }) => void;
  }): void;
  renderButton(element: HTMLElement, options: {
    type: 'standard';
    theme: 'outline';
    size: 'large';
    text: 'continue_with';
    locale: string;
    width: number;
  }): void;
}

function identity(): GoogleIdentity | undefined {
  return (window as Window & { google?: { accounts?: { id?: GoogleIdentity } } }).google?.accounts?.id;
}

let loading: Promise<GoogleIdentity> | undefined;

export function loadGoogleIdentity(): Promise<GoogleIdentity> {
  const loaded = identity();
  if (loaded) {
    return Promise.resolve(loaded);
  }

  loading ??= new Promise<GoogleIdentity>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = () => {
      const sdk = identity();
      if (sdk) {
        resolve(sdk);
      } else {
        reject(new Error('Google Identity Services no está disponible.'));
      }
    };
    script.onerror = () => {
      script.remove();
      reject(new Error('No se pudo cargar el acceso con Google.'));
    };
    document.head.append(script);
  }).catch((error: unknown) => {
    loading = undefined;
    throw error;
  });

  return loading;
}
