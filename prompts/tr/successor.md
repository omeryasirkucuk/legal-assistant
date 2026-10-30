Bir kanun maddesi, başka bir kanunun maddesine atıf yapıyor. Atıf yapılan kanun ya yürürlükten kalkmış (yerine yeni bir kanun gelmiş, madde numaraları değişmiş) ya da elimizdeki dizinde yok. Sana atıf yapan cümle ve bugünkü kanunlardan içerikçe benzer aday maddeler verilir.

Görevin: atıf yapılan hükmün bugün hangi aday maddede düzenlendiğini bulmak. Önce referenced_rule alanına atıf yapan cümlenin, atıf yaptığı maddeden tam olarak neyi aldığını kısaca yaz (bir ihtar, bir süre, bir şart, bir usul). Sonra review alanında aday listesindeki her madde için bir kayıt yaz: sets_referenced_rule, maddenin metni bu kuralın kendisini koyuyorsa true, koymuyorsa false. Aynı konudaki komşu bir hüküm (aynı sözleşme türünün başka bir sona erme sebebi gibi) yeterli değildir.

Hafızandaki bilgiyi (örneğin eski ve yeni kanun arasındaki madde karşılıklarını) yalnızca hangi adayın doğru olduğunu belirlemek için kullan; seçtiğin maddenin metni de o kuralı gerçekten içermeli.

Atıfta sayılan her madde için en fazla bir adayı true yap. Karşılığı adaylar arasında yoksa ya da emin değilsen false yaz. article alanına aday listesindeki madde numarasını aynen yaz.
