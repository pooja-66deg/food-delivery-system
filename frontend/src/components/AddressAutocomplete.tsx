import React, { useEffect, useRef, useState } from 'react';

// Type definitions for Google Maps API
interface AutocompleteService {
  getPlacePredictions(request: {
    input: string;
    componentRestrictions?: { country: string };
  }): Promise<{ predictions: unknown[] }>;
}

interface PlacesService {
  findPlaceFromQuery(
    request: {
      query: string;
      fields: string[];
    },
    callback: (results: PlaceResult[] | null, status: string) => void
  ): void;
}

interface PlaceResult {
  formatted_address?: string;
  address_components?: AddressComponent[];
  geometry?: {
    location: { lat: number; lng: number };
  };
  place_id?: string;
}

interface AddressComponent {
  long_name: string;
  short_name: string;
  types: string[];
}

interface AddressComponents {
  line1: string;
  line2: string;
  city: string;
  postal_code: string;
}

interface AddressAutocompleteProps {
  onAddressSelect: (address: AddressComponents) => void;
  disabled?: boolean;
  placeholder?: string;
}

export const AddressAutocomplete: React.FC<AddressAutocompleteProps> = ({
  onAddressSelect,
  disabled = false,
  placeholder = 'Start typing your address...',
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [useFallback, setUseFallback] = useState(false);
  const [value, setValue] = useState('');
  const autocompleteRef = useRef<AutocompleteService | null>(null);
  const placesServiceRef = useRef<PlacesService | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const googleRef = useRef<any>(null);

  // Initialize Google Places API
  useEffect(() => {
    const initializeGooglePlaces = async () => {
      try {
        const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
        if (!apiKey) {
          console.warn('Google Maps API key not configured - using fallback');
          setUseFallback(true);
          return;
        }

        // Load the Google Maps API script
        const loadGoogleMaps = (): Promise<void> => {
          return new Promise((resolve, reject) => {
            // Check if already loaded
            const win = window as unknown as Record<string, unknown>;
            if (win.google) {
              googleRef.current = win.google;
              resolve();
              return;
            }

            const script = document.createElement('script');
            script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`;
            script.async = true;
            script.defer = true;
            script.onload = () => {
              const win2 = window as unknown as Record<string, unknown>;
              googleRef.current = win2.google;
              resolve();
            };
            script.onerror = () => {
              reject(new Error('Failed to load Google Maps API'));
            };
            document.head.appendChild(script);
          });
        };

        await loadGoogleMaps();

        if (inputRef.current && googleRef.current) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          autocompleteRef.current = new (googleRef.current as any).maps.places.AutocompleteService();
          const dummyMap = document.createElement('div');
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          placesServiceRef.current = new (googleRef.current as any).maps.places.PlacesService(dummyMap);
        }
      } catch (error) {
        console.error('Failed to initialize Google Places:', error);
        setUseFallback(true);
      }
    };

    initializeGooglePlaces();
  }, []);

  // Handle autocomplete input
  const handleInputChange = async (inputValue: string) => {
    setValue(inputValue);

    if (!inputValue.trim() || useFallback || !autocompleteRef.current) {
      return;
    }

    try {
      void autocompleteRef.current.getPlacePredictions({
        input: inputValue,
        componentRestrictions: { country: 'us' },
      });

      // For now, we'll handle selection in the handleSelectPlace function
      // This is a simplified version - you can enhance with a dropdown UI
    } catch (error) {
      console.error('Autocomplete error:', error);
    }
  };

  // Handle place selection
  const handleSelectPlace = (event: React.KeyboardEvent) => {
    if (event.key !== 'Enter' || !value.trim() || useFallback || !placesServiceRef.current) {
      return;
    }

    event.preventDefault();

    try {
      const request = {
        query: value,
        fields: ['formatted_address', 'address_components', 'geometry', 'place_id'],
      };

      placesServiceRef.current.findPlaceFromQuery(
        request,
        (results: PlaceResult[] | null, status: string) => {
          if (status === 'OK' && results && results[0]) {
            const place = results[0];
            const components = extractAddressComponents(place);
            onAddressSelect(components);
            setValue(''); // Clear input after selection
          }
        }
      );
    } catch (error) {
      console.error('Place selection error:', error);
    }
  };

  // Extract address components from Google Place object
  const extractAddressComponents = (place: PlaceResult): AddressComponents => {
    let line1 = '';
    let line2 = '';
    let city = '';
    let postal_code = '';

    if (place.address_components) {
      place.address_components.forEach((component: AddressComponent) => {
        const types = component.types;

        if (types.includes('street_number') || types.includes('route')) {
          if (types.includes('street_number')) {
            line1 = component.long_name + ' ' + line1;
          } else {
            line1 += component.long_name;
          }
        }

        if (types.includes('premise') || types.includes('subpremise')) {
          line2 = component.long_name;
        }

        if (types.includes('locality') || types.includes('postal_town')) {
          city = component.long_name;
        }

        if (types.includes('postal_code')) {
          postal_code = component.long_name;
        }
      });
    }

    // Fallback to formatted address if components unavailable
    if (!line1 && place.formatted_address) {
      const parts = place.formatted_address.split(',');
      line1 = parts[0]?.trim() || place.formatted_address;
      if (parts.length > 1) city = parts[parts.length - 2]?.trim() || '';
      if (parts.length > 2) postal_code = parts[parts.length - 1]?.trim() || '';
    }

    return {
      line1: line1.trim(),
      line2: line2.trim(),
      city: city.trim(),
      postal_code: postal_code.trim(),
    };
  };

  // Fallback to simple text input
  if (useFallback) {
    return (
      <div>
        <label className="block text-sm font-medium mb-2">Street Address</label>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          className="w-full px-3 py-2 border border-gray-300 rounded-md"
        />
        <p className="text-gray-500 text-xs mt-1">Google Maps API not configured</p>
      </div>
    );
  }

  return (
    <div>
      <label className="block text-sm font-medium mb-2">Street Address</label>
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => handleInputChange(e.target.value)}
        onKeyDown={handleSelectPlace}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full px-3 py-2 border border-gray-300 rounded-md"
      />
      <p className="text-gray-500 text-xs mt-1">Press Enter to select address</p>
    </div>
  );
};
