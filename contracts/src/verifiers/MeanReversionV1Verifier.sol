// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MeanReversionV1Verifier {
    // Scalar field size
    uint256 constant r =
        21_888_242_871_839_275_222_246_405_745_257_275_088_548_364_400_416_034_343_698_204_186_575_808_495_617;
    // Base field size
    uint256 constant q =
        21_888_242_871_839_275_222_246_405_745_257_275_088_696_311_157_297_823_662_689_037_894_645_226_208_583;

    // Verification Key data
    uint256 constant alphax =
        20_491_192_805_390_485_299_153_009_773_594_534_940_189_261_866_228_447_918_068_658_471_970_481_763_042;
    uint256 constant alphay =
        9_383_485_363_053_290_200_918_347_156_157_836_566_562_967_994_039_712_273_449_902_621_266_178_545_958;
    uint256 constant betax1 =
        4_252_822_878_758_300_859_123_897_981_450_591_353_533_073_413_197_771_768_651_442_665_752_259_397_132;
    uint256 constant betax2 =
        6_375_614_351_688_725_206_403_948_262_868_962_793_625_744_043_794_305_715_222_011_528_459_656_738_731;
    uint256 constant betay1 =
        21_847_035_105_528_745_403_288_232_691_147_584_728_191_162_732_299_865_338_377_159_692_350_059_136_679;
    uint256 constant betay2 =
        10_505_242_626_370_262_277_552_901_082_094_356_697_409_835_680_220_590_971_873_171_140_371_331_206_856;
    uint256 constant gammax1 =
        11_559_732_032_986_387_107_991_004_021_392_285_783_925_812_861_821_192_530_917_403_151_452_391_805_634;
    uint256 constant gammax2 =
        10_857_046_999_023_057_135_944_570_762_232_829_481_370_756_359_578_518_086_990_519_993_285_655_852_781;
    uint256 constant gammay1 =
        4_082_367_875_863_433_681_332_203_403_145_435_568_316_851_327_593_401_208_105_741_076_214_120_093_531;
    uint256 constant gammay2 =
        8_495_653_923_123_431_417_604_973_247_489_272_438_418_190_587_263_600_148_770_280_649_306_958_101_930;
    uint256 constant deltax1 =
        16_527_273_070_363_033_021_338_165_286_939_290_235_762_996_222_335_075_721_838_567_610_613_443_036_549;
    uint256 constant deltax2 =
        3_095_295_958_496_513_171_931_357_642_028_840_209_651_594_051_753_897_972_410_674_770_143_240_227_306;
    uint256 constant deltay1 =
        10_348_865_155_222_181_560_748_905_770_466_920_880_140_590_742_012_785_499_320_575_538_361_000_437_066;
    uint256 constant deltay2 =
        17_325_855_706_760_832_958_178_959_436_159_744_350_887_850_561_484_907_787_497_631_470_609_146_105_867;

    uint256 constant IC0x =
        14_903_916_098_792_609_176_212_278_359_527_077_606_560_205_193_021_108_670_502_301_311_489_979_598_775;
    uint256 constant IC0y =
        16_069_868_390_232_463_649_950_435_001_998_655_554_855_088_180_480_429_441_679_526_676_962_483_426_997;

    uint256 constant IC1x =
        14_668_513_571_908_500_479_677_880_249_043_513_730_003_747_459_957_601_469_504_188_097_362_345_376_212;
    uint256 constant IC1y =
        1_685_509_375_361_198_643_050_959_706_833_466_561_379_784_958_578_258_638_693_798_877_748_327_493_483;

    uint256 constant IC2x =
        8_862_808_626_155_896_061_569_800_745_698_531_290_614_268_113_228_956_637_364_592_991_171_478_965_416;
    uint256 constant IC2y =
        12_531_720_828_173_729_213_268_254_702_241_434_704_648_255_241_126_355_438_533_488_860_408_811_992_853;

    uint256 constant IC3x =
        7_720_532_928_168_117_149_788_151_410_608_074_632_093_161_254_929_660_829_209_461_307_821_454_295_980;
    uint256 constant IC3y =
        20_663_591_999_106_578_516_448_572_805_649_840_682_699_212_555_045_766_185_061_599_733_800_420_785_922;

    uint256 constant IC4x =
        16_196_302_776_265_148_751_050_650_472_189_493_662_613_114_499_436_101_040_401_138_021_667_636_795_512;
    uint256 constant IC4y =
        21_215_144_136_212_295_215_704_473_962_951_635_214_358_877_347_674_542_191_602_326_586_571_780_760_695;

    uint256 constant IC5x =
        6_460_332_448_009_731_950_033_451_580_878_286_007_945_957_631_164_417_276_529_628_922_773_601_948_127;
    uint256 constant IC5y =
        853_260_698_363_744_696_869_649_585_581_001_201_050_022_377_738_955_316_978_979_739_414_625_466_603;

    uint256 constant IC6x =
        3_552_600_836_366_109_099_049_962_377_619_155_975_096_826_977_125_029_327_965_662_512_065_732_298_931;
    uint256 constant IC6y =
        17_435_820_377_192_415_048_506_011_072_402_102_756_887_747_058_557_560_973_547_344_188_410_841_016_606;

    uint256 constant IC7x =
        11_298_090_643_783_900_065_413_539_527_904_110_799_697_099_012_195_944_015_551_111_757_616_237_882_781;
    uint256 constant IC7y =
        17_212_768_870_838_780_666_086_931_999_666_153_910_096_306_419_323_809_614_778_145_033_581_132_923_503;

    uint256 constant IC8x =
        18_464_019_465_204_476_541_965_980_656_981_887_724_200_477_080_174_699_140_537_550_906_570_367_747_712;
    uint256 constant IC8y =
        6_868_657_395_638_293_580_025_523_965_284_183_818_656_019_025_747_991_289_872_042_169_576_932_608_634;

    uint256 constant IC9x =
        5_971_928_072_339_837_474_563_441_165_105_585_802_721_087_102_411_943_190_545_657_589_281_986_423_815;
    uint256 constant IC9y =
        5_900_862_468_953_651_538_110_214_050_082_934_457_449_231_543_381_603_622_359_055_657_599_111_663_957;

    uint256 constant IC10x =
        10_724_712_155_496_879_344_099_284_826_362_968_033_383_923_069_664_891_481_172_216_025_615_600_889_890;
    uint256 constant IC10y =
        14_882_316_556_783_065_155_153_908_843_064_864_317_388_361_582_836_993_671_250_096_482_520_777_842_038;

    uint256 constant IC11x =
        681_429_776_082_964_532_483_843_670_881_497_762_038_877_999_706_492_357_416_553_711_013_752_767_533;
    uint256 constant IC11y =
        7_002_771_210_183_828_922_490_115_792_643_768_463_087_833_620_855_092_376_013_435_946_215_447_961_317;

    uint256 constant IC12x =
        3_717_696_460_758_314_786_775_487_610_984_099_794_152_217_543_611_835_098_316_482_141_356_167_390_653;
    uint256 constant IC12y =
        11_722_366_187_845_627_697_476_642_343_918_919_634_156_960_908_391_050_405_583_092_133_386_249_513_144;

    uint256 constant IC13x =
        18_659_203_229_226_721_930_865_667_374_454_326_556_897_083_211_847_433_073_054_111_453_892_512_865_627;
    uint256 constant IC13y =
        18_643_309_936_016_013_576_632_640_937_023_199_502_627_591_355_989_224_317_023_333_732_178_678_207_781;

    uint256 constant IC14x =
        16_286_861_589_448_304_729_880_954_038_548_806_526_420_833_689_958_266_755_046_067_074_194_824_671_622;
    uint256 constant IC14y =
        9_809_970_518_073_868_426_556_748_690_407_440_810_218_286_109_121_387_141_814_648_741_484_427_573_414;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[14] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))

                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))

                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))

                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))

                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))

                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))

                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))

                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            checkField(calldataload(add(_pubSignals, 192)))

            checkField(calldataload(add(_pubSignals, 224)))

            checkField(calldataload(add(_pubSignals, 256)))

            checkField(calldataload(add(_pubSignals, 288)))

            checkField(calldataload(add(_pubSignals, 320)))

            checkField(calldataload(add(_pubSignals, 352)))

            checkField(calldataload(add(_pubSignals, 384)))

            checkField(calldataload(add(_pubSignals, 416)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
