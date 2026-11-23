using System.Collections.ObjectModel;

// ItemsSource is object-typed, so automatic ABI inference cannot always see
// this external generic instantiation. Retain generated WinRT collection and
// notification vtables in the actual trimmed Portable artifact.
[assembly: WinRT.GeneratedWinRTExposedExternalType(typeof(ObservableCollection<string>))]
